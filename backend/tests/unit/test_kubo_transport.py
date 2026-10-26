"""Wire-level regression: Kubo may fail only in a trailer after HTTP 200."""

from __future__ import annotations

import asyncio
import logging
import traceback
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpcore
import httpx
import pytest

from quantum_backend_v2.content._transport import KuboRPCTransport, _TrailerStream

SECRET = "synthetic-trailer-secret-not-a-real-credential"
BODY = b'{"Hash":"fixture","Size":"1"}\n'


def wire_response(error: bytes = b"", *, close: bool = True) -> bytes:
    connection = b"close" if close else b"keep-alive"
    return (
        b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n"
        b"Trailer: X-Stream-Error\r\nConnection: "
        + connection
        + b"\r\n\r\n"
        + f"{len(BODY):x}\r\n".encode()
        + BODY
        + b"\r\n0\r\n"
        + (b"X-Stream-Error: " + error + b"\r\n" if error else b"")
        + b"\r\n"
    )


@asynccontextmanager
async def wire_server(
    response: bytes,
    *,
    fragment: int = 7,
    connections: list[int] | None = None,
) -> AsyncIterator[str]:
    tasks: set[asyncio.Task[None]] = set()

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        task = asyncio.current_task()
        assert task is not None
        tasks.add(task)
        if connections is not None:
            connections.append(writer.get_extra_info("peername")[1])
        try:
            while True:
                try:
                    await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=2)
                except (asyncio.IncompleteReadError, ConnectionResetError):
                    return
                for offset in range(0, len(response), fragment):
                    writer.write(response[offset : offset + fragment])
                    await writer.drain()
                    await asyncio.sleep(0)
                if b"Connection: close" in response:
                    return
        except (ConnectionError, asyncio.TimeoutError):
            return
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except ConnectionError:
                pass
            finally:
                tasks.discard(task)

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    try:
        async with server:
            yield f"http://127.0.0.1:{port}/api/v0/add"
    finally:
        server.close()
        await server.wait_closed()
        pending = list(tasks)
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)


@pytest.mark.anyio
@pytest.mark.parametrize("fragment", [1, 7, 65536])
async def test_late_stream_error_cannot_be_reported_as_success(
    fragment: int,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    async with wire_server(wire_response(SECRET.encode()), fragment=fragment) as url:
        async with httpx.AsyncClient(
            transport=KuboRPCTransport(), trust_env=False, timeout=2
        ) as client:
            with pytest.raises(httpx.TransportError) as caught:
                await client.post(url)
    diagnostic = "".join(
        traceback.format_exception(type(caught.value), caught.value, caught.value.__traceback__)
    )
    assert type(caught.value) is httpx.TransportError
    assert SECRET not in diagnostic + str(caught.value) + repr(caught.value) + caplog.text


@pytest.mark.anyio
@pytest.mark.parametrize("prefix", [b"", b"HTTP/1.1 100 Continue\r\n\r\n"])
async def test_successful_responses_reuse_connection_without_mixing_parser_state(
    prefix: bytes,
) -> None:
    connections: list[int] = []
    async with wire_server(prefix + wire_response(close=False), connections=connections) as url:
        async with httpx.AsyncClient(
            transport=KuboRPCTransport(), trust_env=False, timeout=2
        ) as client:
            for _ in range(2):
                response = await client.post(url)
                assert response.status_code == 200
                assert response.content == BODY
    assert len(connections) == 1


@pytest.mark.anyio
async def test_failed_stream_is_not_reused() -> None:
    connections: list[int] = []
    async with wire_server(
        wire_response(SECRET.encode(), close=False), connections=connections
    ) as url:
        async with httpx.AsyncClient(
            transport=KuboRPCTransport(), trust_env=False, timeout=2
        ) as client:
            for _ in range(2):
                with pytest.raises(httpx.TransportError):
                    await client.post(url)
    assert len(connections) == 2


@pytest.mark.anyio
@pytest.mark.parametrize(
    "wire",
    [
        wire_response()[:-3],
        b"HTTP/1.1 200 OK\r\n" + SECRET.encode() + b"\r\n\r\n",
        wire_response().replace(
            b"Trailer: X-Stream-Error\r\n", b"X-Stream-Error: " + SECRET.encode() + b"\r\n"
        ),
    ],
)
async def test_invalid_or_error_responses_fail_without_exposing_server_text(wire: bytes) -> None:
    async with wire_server(wire, fragment=65536) as url:
        async with httpx.AsyncClient(
            transport=KuboRPCTransport(), trust_env=False, timeout=2
        ) as client:
            with pytest.raises(httpx.TransportError) as caught:
                await client.post(url)
    diagnostic = "".join(
        traceback.format_exception(type(caught.value), caught.value, caught.value.__traceback__)
    )
    assert SECRET not in diagnostic + repr(caught.value)


@pytest.mark.anyio
async def test_bytewise_network_reads_cannot_hide_the_error_trailer() -> None:
    raw = wire_response(SECRET.encode())
    stream = _TrailerStream(httpcore.AsyncMockStream([bytes([value]) for value in raw]))
    received = bytearray()
    try:
        with pytest.raises(httpcore.ReadError) as caught:
            for _ in range(len(raw)):
                received.extend(await stream.read(1))
        assert BODY in received
        assert SECRET not in str(caught.value)
    finally:
        await stream.aclose()


@pytest.mark.anyio
async def test_non_rpc_methods_are_rejected_before_connecting() -> None:
    async with httpx.AsyncClient(transport=KuboRPCTransport(), trust_env=False) as client:
        with pytest.raises(httpx.UnsupportedProtocol):
            await client.get("http://127.0.0.1:1/")
