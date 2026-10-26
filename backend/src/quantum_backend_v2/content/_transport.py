"""Preserve Kubo late-error semantics using public HTTPX/httpcore/h11 interfaces."""

from __future__ import annotations

import ssl
from collections.abc import AsyncIterator, Iterable, Iterator
from contextlib import contextmanager
from typing import Any

import h11
import httpcore
import httpx


@contextmanager
def _mapped_errors() -> Iterator[None]:
    try:
        yield
    except httpcore.TimeoutException:
        raise httpx.TimeoutException("Kubo RPC transport timed out") from None
    except (httpcore.NetworkError, httpcore.ProtocolError):
        raise httpx.TransportError("Kubo RPC transport failed") from None


class _TrailerStream(httpcore.AsyncNetworkStream):
    def __init__(self, stream: httpcore.AsyncNetworkStream) -> None:
        self._stream = stream
        self._complete = True
        self._parser = h11.Connection(h11.CLIENT)

    def _observe(self, data: bytes) -> None:
        if self._complete:
            self._parser = h11.Connection(h11.CLIENT)
            # Only POST is supported. No real request headers/body enter the observer.
            self._parser.send(h11.Request(method=b"POST", target=b"/", headers=[(b"Host", b"rpc")]))
            self._parser.send(h11.EndOfMessage())
            self._complete = False
        try:
            self._parser.receive_data(data)
            while True:
                event = self._parser.next_event()
                if (
                    event is h11.NEED_DATA
                    or event is h11.PAUSED
                    or isinstance(event, h11.ConnectionClosed)
                ):
                    return
                if isinstance(event, (h11.Response, h11.EndOfMessage)):
                    if any(
                        key.lower() == b"x-stream-error" and value for key, value in event.headers
                    ):
                        # Do not retain or echo the potentially sensitive server error.
                        raise httpcore.ReadError("Kubo RPC stream failed")
                if isinstance(event, h11.EndOfMessage):
                    self._complete = True
                    return
        except h11.RemoteProtocolError:
            raise httpcore.ReadError("Invalid Kubo RPC response framing") from None

    async def read(self, max_bytes: int, timeout: float | None = None) -> bytes:
        data = await self._stream.read(max_bytes, timeout)
        self._observe(data)
        return data

    async def write(self, buffer: bytes, timeout: float | None = None) -> None:
        await self._stream.write(buffer, timeout)

    async def aclose(self) -> None:
        await self._stream.aclose()

    async def start_tls(
        self,
        ssl_context: ssl.SSLContext,
        server_hostname: str | None = None,
        timeout: float | None = None,
    ) -> httpcore.AsyncNetworkStream:
        stream = await self._stream.start_tls(ssl_context, server_hostname, timeout)
        return _TrailerStream(stream)

    def get_extra_info(self, info: str) -> Any:
        return self._stream.get_extra_info(info)


class _TrailerBackend(httpcore.AsyncNetworkBackend):
    def __init__(self) -> None:
        self._backend = httpcore.AnyIOBackend()

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[httpcore.SOCKET_OPTION] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        return _TrailerStream(
            await self._backend.connect_tcp(
                host,
                port,
                timeout,
                local_address,
                socket_options,
            )
        )

    async def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,
        socket_options: Iterable[httpcore.SOCKET_OPTION] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        return _TrailerStream(
            await self._backend.connect_unix_socket(path, timeout, socket_options)
        )

    async def sleep(self, seconds: float) -> None:
        await self._backend.sleep(seconds)


class _ResponseStream(httpx.AsyncByteStream):
    def __init__(self, response: httpcore.Response) -> None:
        self._response = response

    async def __aiter__(self) -> AsyncIterator[bytes]:
        with _mapped_errors():
            async for chunk in self._response.aiter_stream():
                yield chunk

    async def aclose(self) -> None:
        with _mapped_errors():
            await self._response.aclose()


class KuboRPCTransport(httpx.AsyncBaseTransport):
    """HTTP/1.1 POST transport that rejects late errors before body consumption ends.

    httpcore still owns connections, TLS, timeouts and framing. A passive h11
    observer catches trailers which its standard HTTPX adapter otherwise drops.
    """

    def __init__(self) -> None:
        self._pool = httpcore.AsyncConnectionPool(
            ssl_context=httpcore.default_ssl_context(),
            max_connections=10,
            max_keepalive_connections=5,
            keepalive_expiry=5.0,
            http1=True,
            http2=False,
            network_backend=_TrailerBackend(),
            retries=0,
        )

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if request.method != "POST" or request.url.scheme not in {"http", "https"}:
            raise httpx.UnsupportedProtocol("Kubo RPC transport requires HTTP(S) POST")
        if not isinstance(request.stream, httpx.AsyncByteStream):
            raise httpx.RequestError("Kubo RPC requires an asynchronous request stream")
        with _mapped_errors():
            response = await self._pool.handle_async_request(
                httpcore.Request(
                    method=request.method,
                    url=httpcore.URL(
                        scheme=request.url.raw_scheme,
                        host=request.url.raw_host,
                        port=request.url.port,
                        target=request.url.raw_path,
                    ),
                    headers=request.headers.raw,
                    content=request.stream,
                    extensions=request.extensions,
                )
            )
        return httpx.Response(
            status_code=response.status,
            headers=response.headers,
            stream=_ResponseStream(response),
            extensions=response.extensions,
        )

    async def aclose(self) -> None:
        with _mapped_errors():
            await self._pool.aclose()
