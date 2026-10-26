"""Fail-closed response handling around the typed Kubo client."""

from __future__ import annotations

import asyncio
import logging
import traceback
from collections.abc import AsyncIterator

import httpx
import pytest

from quantum_backend_v2.config import KuboSettings
from quantum_backend_v2.content.kubo import (
    KuboClient,
    KuboRejectedError,
    KuboUnavailableError,
)

SECRET = "fixture-safety-token-with-at-least-32-characters"
CID = "bafkreiblu5p7tt3uueqioo66yogr4ybujviw5wldtzhuzivntx2wjgrmqi"


def settings(**overrides: object) -> KuboSettings:
    return KuboSettings.model_validate({"rpc_secret": SECRET, **overrides})


@pytest.mark.anyio
@pytest.mark.parametrize(
    "method,payload",
    [
        ("add", {"Name": "content", "Size": "1"}),
        ("add", {"Name": "content", "Hash": CID, "Size": True}),
        ("add", {"Name": "content", "Hash": CID, "Size": "-1"}),
        ("pin_add", {"Pins": []}),
        ("pin_rm", {"Pins": [None]}),
        ("pin_ls", {"Keys": {CID: {"Type": "unknown"}}}),
        ("block_stat", {"Key": CID, "Size": SECRET}),
    ],
)
async def test_malformed_success_is_not_a_content_mismatch_or_rejection(
    method: str, payload: dict[str, object]
) -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
    async with KuboClient(settings(), transport=transport) as client:
        argument = b"data" if method == "add" else CID
        with pytest.raises(KuboUnavailableError) as caught:
            await getattr(client, method)(argument)
    diagnostic = "".join(
        traceback.format_exception(type(caught.value), caught.value, caught.value.__traceback__)
    )
    assert SECRET not in diagnostic + repr(caught.value)


@pytest.mark.anyio
@pytest.mark.parametrize(
    "body",
    [
        b'{"Stats":{"BlockCount":0,"BlockBytesCount":0}}\n{"Stats":{"BlockCount":0,"BlockBytesCount":0}}\n',
        b'{"Root":null,"Stats":null}\n',
        b'{"Stats":{"BlockCount":true,"BlockBytesCount":0}}\n',
        b'{"Stats":{"BlockCount":0,"BlockBytesCount":-1}}\n',
    ],
)
async def test_car_invalid_events_are_unavailable(body: bytes) -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, content=body))
    async with KuboClient(settings(), transport=transport) as client:
        with pytest.raises(KuboUnavailableError):
            await client.dag_import(b"car")


@pytest.mark.anyio
async def test_rootless_car_can_succeed_without_claiming_pinned_roots() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"Stats": {"BlockCount": 0, "BlockBytesCount": 0}})
    )
    async with KuboClient(settings(), transport=transport) as client:
        result = await client.dag_import(b"car")
    assert result.pinned_roots == ()
    assert result.block_count == 0


@pytest.mark.anyio
async def test_explicit_streamed_rpc_error_is_rejected_without_echoing_it() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"Message": SECRET, "Code": 0, "Type": "error"})
    )
    async with KuboClient(settings(), transport=transport) as client:
        with pytest.raises(KuboRejectedError) as caught:
            await client.block_stat(CID)
    assert SECRET not in str(caught.value)


@pytest.mark.anyio
@pytest.mark.parametrize(
    "headers",
    [
        {"Content-Length": "10000000"},
        {"X-Stream-Error": SECRET},
        {"Content-Encoding": "gzip"},
    ],
)
async def test_unsupported_or_oversized_responses_are_not_read(headers: dict[str, str]) -> None:
    closed = False

    class Stream(httpx.AsyncByteStream):
        async def __aiter__(self) -> AsyncIterator[bytes]:
            raise AssertionError("Must reject the response before reading it")
            yield b""

        async def aclose(self) -> None:
            nonlocal closed
            closed = True

    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, headers=headers, stream=Stream())
    )
    async with KuboClient(settings(), transport=transport) as client:
        with pytest.raises(KuboUnavailableError):
            await client.block_stat(CID)
    assert closed


@pytest.mark.anyio
async def test_complete_json_cannot_hide_a_later_stream_failure(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    caplog.set_level(logging.DEBUG)

    class Stream(httpx.AsyncByteStream):
        async def __aiter__(self) -> AsyncIterator[bytes]:
            yield f'{{"Key":"{CID}","Size":1}}'.encode()
            raise httpx.ReadError(SECRET)

    transport = httpx.MockTransport(lambda request: httpx.Response(200, stream=Stream()))
    # Verify the default factory is used, rather than requiring callers to opt in.
    monkeypatch.setattr("quantum_backend_v2.content.kubo.KuboRPCTransport", lambda: transport)
    async with KuboClient(settings()) as client:
        with pytest.raises(KuboUnavailableError) as caught:
            await client.block_stat(CID)
    diagnostic = "".join(
        traceback.format_exception(type(caught.value), caught.value, caught.value.__traceback__)
    )
    assert SECRET not in diagnostic + caplog.text


@pytest.mark.anyio
async def test_trickled_response_is_bounded_by_total_deadline() -> None:
    closed = False

    class Stream(httpx.AsyncByteStream):
        async def __aiter__(self) -> AsyncIterator[bytes]:
            while True:
                yield b" "
                await asyncio.sleep(0.001)

        async def aclose(self) -> None:
            nonlocal closed
            closed = True

    transport = httpx.MockTransport(lambda request: httpx.Response(200, stream=Stream()))
    async with KuboClient(settings(timeout_seconds=0.02), transport=transport) as client:
        with pytest.raises(KuboUnavailableError):
            await client.block_stat(CID)
    assert closed


@pytest.mark.anyio
async def test_transport_state_error_does_not_escape_with_credentials() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        raise RuntimeError(SECRET)

    async with KuboClient(settings(), transport=httpx.MockTransport(handle)) as client:
        with pytest.raises(KuboUnavailableError) as caught:
            await client.block_stat(CID)
    diagnostic = "".join(
        traceback.format_exception(type(caught.value), caught.value, caught.value.__traceback__)
    )
    assert SECRET not in diagnostic


@pytest.mark.anyio
@pytest.mark.parametrize("cancelled", [False, True])
async def test_cleanup_failure_preserves_primary_failure_or_cancellation(cancelled: bool) -> None:
    class Transport(httpx.MockTransport):
        async def aclose(self) -> None:
            raise httpx.ReadError(SECRET)

    transport = Transport(lambda request: httpx.Response(403))
    error = asyncio.CancelledError if cancelled else KuboRejectedError
    with pytest.raises(error):
        async with KuboClient(settings(), transport=transport) as client:
            if cancelled:
                raise asyncio.CancelledError()
            await client.block_stat(CID)


@pytest.mark.anyio
@pytest.mark.parametrize("cid", ["", SECRET, "invalid\ncid"])
async def test_bad_arguments_cannot_leak_credentials_into_request_logs(
    cid: str, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    called = False

    def handle(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200)

    async with KuboClient(settings(), transport=httpx.MockTransport(handle)) as client:
        with pytest.raises(KuboRejectedError):
            await client.block_stat(cid)
    assert not called
    assert SECRET not in caplog.text
