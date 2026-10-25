import asyncio
import hashlib
from unittest.mock import Mock

import httpx
import pytest
from cid import make_cid

from quantum_backend_v2.config import GatewaySettings, load_settings
from quantum_backend_v2.content.gateway import (
    GatewayClient,
    GatewayMismatchError,
    GatewayRejectedError,
    GatewayUnavailableError,
)

pytestmark = pytest.mark.anyio
BODY = b'{"hello":"world"}'


def cid_for(body=BODY, codec="raw", encoding="base32"):
    return make_cid(1, codec, b"\x12\x20" + hashlib.sha256(body).digest()).encode(encoding).decode()


class Stream(httpx.AsyncByteStream):
    def __init__(self, chunks, error=None, delay=0):
        self.chunks = chunks
        self.error = error
        self.delay = delay
        self.closed = False

    async def __aiter__(self):
        for chunk in self.chunks:
            if self.delay:
                await asyncio.sleep(self.delay)
            yield chunk
        if self.error:
            raise self.error

    async def aclose(self):
        self.closed = True


def client_for(stream, *, status=200, headers=None, **settings):
    handler = Mock(
        return_value=httpx.Response(
            status,
            headers={"Content-Type": "application/vnd.ipld.raw", **(headers or {})},
            stream=stream,
        )
    )
    client = GatewayClient(GatewaySettings(**settings), transport=httpx.MockTransport(handler))
    return client, handler


@pytest.mark.parametrize("codec", ["raw", "json", "dag-json"])
@pytest.mark.parametrize("encoding", ["base32", "base58btc", "base16"])
async def test_verified_bytes_and_canonical_request(codec, encoding):
    stream = Stream([BODY[:4], BODY[4:]])
    client, handler = client_for(stream)
    async with client:
        assert await client.fetch(cid_for(codec=codec, encoding=encoding)) == BODY
    request = handler.call_args.args[0]
    assert request.url.path == "/ipfs/" + cid_for(codec=codec)
    assert request.url.params["format"] == "raw"
    assert request.headers["accept"] == "application/vnd.ipld.raw"
    assert request.headers["accept-encoding"] == "identity"
    assert "authorization" not in request.headers
    assert stream.closed


@pytest.mark.parametrize("body", [b"", b"tampered", b'{ "hello": "world" }'])
async def test_different_bytes_are_mismatch_even_for_equivalent_json(body):
    client, _ = client_for(Stream([body]))
    async with client:
        with pytest.raises(GatewayMismatchError):
            await client.fetch(cid_for(codec="dag-json"))


async def test_empty_block_can_verify():
    client, _ = client_for(Stream([]))
    async with client:
        assert await client.fetch(cid_for(b"")) == b""


@pytest.mark.parametrize("status", [206, 301, 302, 404, 429, 500, 504])
async def test_unsuccessful_response_is_unavailable_without_redirect_or_body_read(status):
    stream = Stream([], error=AssertionError("body must not be read"))
    client, handler = client_for(
        stream, status=status, headers={"Location": "http://elsewhere/secret"}
    )
    async with client:
        with pytest.raises(GatewayUnavailableError):
            await client.fetch(cid_for())
    assert handler.call_count == 1
    assert stream.closed


@pytest.mark.parametrize(
    "headers",
    [
        {"Content-Encoding": "gzip"},
        {"Content-Type": "application/json"},
        {"Content-Length": "-1"},
        {"Content-Length": "invalid"},
        {"Content-Length": "100"},
    ],
)
async def test_unsupported_or_oversized_headers_are_unavailable(headers):
    stream = Stream([], error=AssertionError("body must not be read"))
    client, _ = client_for(stream, headers=headers, max_response_bytes=20)
    async with client:
        with pytest.raises(GatewayUnavailableError):
            await client.fetch(cid_for())
    assert stream.closed


async def test_stream_limit_without_content_length():
    stream = Stream([b"123", b"456"], error=AssertionError("must stop at size limit"))
    client, _ = client_for(stream, max_response_bytes=5)
    async with client:
        with pytest.raises(GatewayUnavailableError):
            await client.fetch(cid_for())
    assert stream.closed


async def test_exact_size_limit_is_allowed():
    client, _ = client_for(Stream([BODY]), max_response_bytes=len(BODY))
    async with client:
        assert await client.fetch(cid_for()) == BODY


@pytest.mark.parametrize(
    "error", [httpx.ReadTimeout("synthetic-secret"), httpx.RemoteProtocolError("synthetic-secret")]
)
async def test_interrupted_body_is_unavailable_not_mismatch(error):
    stream = Stream([b"partial"], error=error)
    client, _ = client_for(stream)
    async with client:
        with pytest.raises(GatewayUnavailableError) as caught:
            await client.fetch(cid_for())
    assert "synthetic-secret" not in str(caught.value)
    assert caught.value.__suppress_context__
    assert stream.closed


async def test_truncated_body_is_unavailable():
    client, _ = client_for(Stream([b"part"]), headers={"Content-Length": "20"})
    async with client:
        with pytest.raises(GatewayUnavailableError):
            await client.fetch(cid_for())


async def test_total_deadline_closes_response():
    stream = Stream([b"one", b"two"], delay=0.03)
    client, _ = client_for(stream, timeout_seconds=0.01)
    async with client:
        with pytest.raises(GatewayUnavailableError):
            await client.fetch(cid_for())
    assert stream.closed


async def test_cancellation_propagates_and_closes_response():
    stream = Stream([], error=asyncio.CancelledError())
    client, _ = client_for(stream)
    async with client:
        with pytest.raises(asyncio.CancelledError):
            await client.fetch(cid_for())
    assert stream.closed


@pytest.mark.parametrize(
    "reference",
    [
        "",
        "garbage",
        "b",
        "../secret",
        "https://host/ipfs/x",
        "a" * 513,
        cid_for(codec="dag-pb"),
        make_cid(1, "raw", b"\x00\x03abc").encode("base32").decode(),
    ],
)
async def test_invalid_or_unsupported_cid_is_rejected_before_request(reference):
    client, handler = client_for(Stream([]))
    async with client:
        with pytest.raises(GatewayRejectedError):
            await client.fetch(reference)
    handler.assert_not_called()


@pytest.mark.parametrize(
    "url",
    [
        "",
        "file:///tmp/file",
        "https://user:secret@host",
        "http://host/path",
        "http://host?key=secret",
        "http://host#secret",
        "http://host\n",
    ],
)
def test_invalid_origin_is_rejected_without_echoing_configuration(url):
    with pytest.raises(GatewayRejectedError) as caught:
        GatewayClient(GatewaySettings(url=url))
    assert "secret" not in str(caught.value)


async def test_closed_client_is_unavailable():
    client, handler = client_for(Stream([]))
    await client.aclose()
    with pytest.raises(GatewayUnavailableError):
        await client.fetch(cid_for())
    handler.assert_not_called()


def test_gateway_environment_configuration():
    settings = load_settings(
        env={
            "IPFS_GATEWAY_URL": "http://localhost:8080",
            "IPFS_GATEWAY_TIMEOUT_SECONDS": "2",
            "IPFS_GATEWAY_MAX_RESPONSE_BYTES": "1024",
        }
    )
    assert settings.gateway.url == "http://localhost:8080"
    assert settings.gateway.timeout_seconds == 2
    assert settings.gateway.max_response_bytes == 1024
    assert "localhost" not in repr(settings.gateway)


async def test_known_empty_raw_sha256_cid():
    client, _ = client_for(Stream([]))
    async with client:
        assert (
            await client.fetch("bafkreihdwdcefgh4dqkjv67uzcmw7ojee6xedzdetojuzjevtenxquvyku") == b""
        )


async def test_connection_failure_is_sanitized_and_not_retried():
    handler = Mock(side_effect=httpx.ConnectError("synthetic-response-secret"))
    async with GatewayClient(GatewaySettings(), transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(GatewayUnavailableError) as caught:
            await client.fetch(cid_for())
    assert "synthetic-response-secret" not in str(caught.value)
    assert caught.value.__suppress_context__
    assert handler.call_count == 1


@pytest.mark.parametrize(
    "values",
    [
        {"timeout_seconds": 0},
        {"timeout_seconds": float("nan")},
        {"max_response_bytes": 0},
        {"max_response_bytes": 64 * 1024 * 1024 + 1},
    ],
)
def test_invalid_limits_are_rejected(values):
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        GatewaySettings(**values)
