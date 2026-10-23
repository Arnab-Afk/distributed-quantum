"""RPC contracts and failure/privacy behavior; no external Kubo or credentials."""

from __future__ import annotations

import asyncio
import io
import logging
import traceback
from collections.abc import AsyncIterator

import httpx
import pytest

from quantum_backend_v2.config import KuboSettings
from quantum_backend_v2.content.kubo import KuboClient
from quantum_backend_v2.content.kubo import KuboRejectedError as KuboRejected
from quantum_backend_v2.content.kubo import KuboUnavailableError as KuboUnavailable

SECRET = "fixture-kubo-secret-with-at-least-32-characters"
CID = "bafkreiblu5p7tt3uueqioo66yogr4ybujviw5wldtzhuzivntx2wjgrmqi"


def settings(**overrides: object) -> KuboSettings:
    return KuboSettings.model_validate({"rpc_secret": SECRET, **overrides})


def check_request(request: httpx.Request, operation: str) -> None:
    assert request.method == "POST"
    assert request.url.path == f"/api/v0/{operation}"
    assert request.url.params["encoding"] == "json"
    assert request.headers["Authorization"] == f"Bearer {SECRET}"
    assert request.headers["Accept-Encoding"] == "identity"
    assert request.extensions["timeout"]["read"] == 30


@pytest.mark.anyio
@pytest.mark.parametrize("base", ["http://kubo:5001", "http://kubo:5001/api/v0/"])
async def test_add_multipart_and_typed_result(base: str) -> None:
    async def handle(request: httpx.Request) -> httpx.Response:
        check_request(request, "add")
        assert request.url.params["cid-version"] == "1"
        assert request.url.params["pin"] == "true"
        assert request.url.params["progress"] == "false"
        assert request.url.params["wrap-with-directory"] == "false"
        assert "multipart/form-data" in request.headers["Content-Type"]
        assert b"fixture-upload" in await request.aread()
        return httpx.Response(200, json={"Name": "content", "Hash": CID, "Size": "14"})

    data = io.BytesIO(b"fixture-upload")
    async with KuboClient(settings(rpc_url=base), transport=httpx.MockTransport(handle)) as client:
        result = await client.add(data)
    assert result.cid == CID
    assert result.size_bytes == 14
    assert not data.closed


@pytest.mark.anyio
@pytest.mark.parametrize("method,operation", [("pin_add", "pin/add"), ("pin_rm", "pin/rm")])
async def test_pin_mutation_contracts(method: str, operation: str) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        check_request(request, operation)
        assert request.url.params["arg"] == CID
        assert request.url.params["recursive"] == "true"
        return httpx.Response(200, json={"Pins": [CID]})

    async with KuboClient(settings(), transport=httpx.MockTransport(handle)) as client:
        result = await getattr(client, method)(CID)
    assert result.pins == (CID,)


@pytest.mark.anyio
@pytest.mark.parametrize(
    "payload", [{}, {"Keys": {}}, {"Keys": {CID: {"Type": "recursive", "Name": ""}}}]
)
async def test_pin_listing_contract(payload: dict[str, object]) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        check_request(request, "pin/ls")
        assert request.url.params["stream"] == "false"
        assert request.url.params["arg"] == CID
        return httpx.Response(200, json=payload)

    async with KuboClient(settings(), transport=httpx.MockTransport(handle)) as client:
        result = await client.pin_ls(CID)
    keys = payload.get("Keys", {})
    assert isinstance(keys, dict)
    assert len(result.pins) == len(keys)


@pytest.mark.anyio
async def test_block_stat_contract() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        check_request(request, "block/stat")
        assert request.url.params["arg"] == CID
        return httpx.Response(200, json={"Key": CID, "Size": 17})

    async with KuboClient(settings(), transport=httpx.MockTransport(handle)) as client:
        result = await client.block_stat(CID)
    assert (result.cid, result.size_bytes) == (CID, 17)


@pytest.mark.anyio
@pytest.mark.parametrize("pin_roots", [True, False])
async def test_car_import_parses_root_and_terminal_stats(pin_roots: bool) -> None:
    async def handle(request: httpx.Request) -> httpx.Response:
        check_request(request, "dag/import")
        assert request.url.params["pin-roots"] == str(pin_roots).lower()
        assert request.url.params["stats"] == "true"
        assert b"opaque-car-fixture" in await request.aread()
        root = f'{{"Root":{{"Cid":{{"/":"{CID}"}},"PinErrorMsg":""}}}}\n'
        body = (root if pin_roots else "") + '{"Stats":{"BlockCount":1,"BlockBytesCount":17}}\n'
        return httpx.Response(200, content=body)

    async with KuboClient(settings(), transport=httpx.MockTransport(handle)) as client:
        result = await client.dag_import(b"opaque-car-fixture", pin_roots=pin_roots)
    assert result.pinned_roots == ((CID,) if pin_roots else ())
    assert (result.block_count, result.block_bytes) == (1, 17)


@pytest.mark.anyio
@pytest.mark.parametrize("status", [400, 401, 403, 404, 413, 302, 408, 429, 500, 503])
async def test_http_failure_category_without_echoing_response(status: int) -> None:
    calls = 0

    def handle(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            status, text=SECRET, headers={"Location": f"https://elsewhere.invalid/{SECRET}"}
        )

    error_type = KuboUnavailable if status in {408, 429} or status >= 500 else KuboRejected
    async with KuboClient(settings(), transport=httpx.MockTransport(handle)) as client:
        with pytest.raises(error_type) as caught:
            await client.block_stat(CID)
    assert caught.value.status_code == status
    assert SECRET not in str(caught.value) + repr(caught.value)
    assert calls == 1


@pytest.mark.anyio
@pytest.mark.parametrize(
    "error_type", [httpx.ReadTimeout, httpx.ConnectError, httpx.RemoteProtocolError]
)
async def test_transport_failures_are_unavailable_and_private(
    error_type: type[httpx.RequestError], caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)

    def handle(request: httpx.Request) -> httpx.Response:
        raise error_type(SECRET, request=request)

    async with KuboClient(settings(), transport=httpx.MockTransport(handle)) as client:
        with pytest.raises(KuboUnavailable) as caught:
            await client.block_stat(CID)
    diagnostic = "".join(
        traceback.format_exception(type(caught.value), caught.value, caught.value.__traceback__)
    )
    assert SECRET not in diagnostic + caplog.text + repr(caught.value)


@pytest.mark.anyio
@pytest.mark.parametrize(
    "body",
    [
        b"",
        b"<html>broken</html>",
        b"[]",
        b'{"Key":"x","Size":-1}',
        b'{"Key":"x","Size":true}',
        b'{"Key":"x","Size":1,"Size":2}',
        b'{"Key":"x","Size":',
    ],
)
async def test_invalid_response_is_unavailable(body: bytes) -> None:
    async with KuboClient(
        settings(), transport=httpx.MockTransport(lambda request: httpx.Response(200, content=body))
    ) as client:
        with pytest.raises(KuboUnavailable):
            await client.block_stat(CID)


@pytest.mark.anyio
async def test_car_root_pin_failure_is_not_success() -> None:
    body = f'{{"Root":{{"Cid":{{"/":"{CID}"}},"PinErrorMsg":"{SECRET}"}}}}\n'
    body += '{"Stats":{"BlockCount":1,"BlockBytesCount":17}}\n'
    async with KuboClient(
        settings(), transport=httpx.MockTransport(lambda request: httpx.Response(200, content=body))
    ) as client:
        with pytest.raises(KuboRejected) as caught:
            await client.dag_import(b"car")
    assert SECRET not in str(caught.value)


@pytest.mark.anyio
async def test_partial_car_response_without_stats_is_unavailable() -> None:
    body = f'{{"Root":{{"Cid":{{"/":"{CID}"}},"PinErrorMsg":""}}}}\n'
    async with KuboClient(
        settings(), transport=httpx.MockTransport(lambda request: httpx.Response(200, content=body))
    ) as client:
        with pytest.raises(KuboUnavailable):
            await client.dag_import(b"car")


@pytest.mark.anyio
async def test_total_deadline_and_cancellation_are_distinct() -> None:
    async def handle(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(60)
        return httpx.Response(200)

    async with KuboClient(
        settings(timeout_seconds=0.01), transport=httpx.MockTransport(handle)
    ) as client:
        with pytest.raises(KuboUnavailable):
            await client.block_stat(CID)
    async with KuboClient(settings(), transport=httpx.MockTransport(handle)) as client:
        task = asyncio.create_task(client.block_stat(CID))
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


@pytest.mark.anyio
async def test_response_limit_is_applied_while_streaming() -> None:
    closed = False

    class Stream(httpx.AsyncByteStream):
        async def __aiter__(self) -> AsyncIterator[bytes]:
            yield b"x" * 32
            yield b"x" * 32
            raise AssertionError("Must stop reading at the configured budget")

        async def aclose(self) -> None:
            nonlocal closed
            closed = True

    async with KuboClient(
        settings(max_response_bytes=40),
        transport=httpx.MockTransport(lambda request: httpx.Response(200, stream=Stream())),
    ) as client:
        with pytest.raises(KuboUnavailable):
            await client.block_stat(CID)
    assert closed


@pytest.mark.parametrize(
    "url",
    [
        f"http://user:{SECRET}@kubo:5001",
        f"http://kubo:5001/?key={SECRET}",
        f"http://kubo:5001/#{SECRET}",
        f"http://{SECRET}:5001",
        "ftp://kubo:5001",
        "http://kubo:5001/unexpected",
        "not-a-url",
    ],
)
def test_unsafe_configuration_is_rejected_without_echoing_values(url: str) -> None:
    with pytest.raises(KuboRejected) as caught:
        KuboClient(settings(rpc_url=url))
    assert SECRET not in str(caught.value) + repr(caught.value)


def test_missing_secret_is_only_rejected_when_client_is_requested() -> None:
    with pytest.raises(KuboRejected):
        KuboClient(KuboSettings())


@pytest.mark.anyio
async def test_client_closes_owned_session() -> None:
    class Transport(httpx.MockTransport):
        closed = False

        async def aclose(self) -> None:
            self.closed = True

    transport = Transport(lambda request: httpx.Response(200, json={"Key": CID, "Size": 1}))
    async with KuboClient(settings(), transport=transport) as client:
        await client.block_stat(CID)
    assert transport.closed
    with pytest.raises(KuboUnavailable):
        await client.block_stat(CID)
