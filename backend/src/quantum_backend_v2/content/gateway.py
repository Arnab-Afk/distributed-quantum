"""Fetch individual IPFS blocks and verify their exact bytes before returning them."""

from __future__ import annotations

import asyncio
import hashlib
import re
from types import TracebackType

import httpx
from cid import CIDv1, make_cid  # type: ignore[import-untyped]

from quantum_backend_v2.config import GatewaySettings


class GatewayError(Exception):
    """Sanitized gateway failure without endpoint, response text or content."""


class GatewayRejectedError(GatewayError):
    """Invalid configuration or an invalid/unsupported CID; no request was sent."""


class GatewayUnavailableError(GatewayError):
    """A complete successful block response could not be obtained within limits."""


class GatewayMismatchError(GatewayError):
    """The complete block does not match the requested CID."""


def _parse_cid(value: str) -> CIDv1:
    if not isinstance(value, str) or re.fullmatch(r"[A-Za-z0-9]{1,512}", value) is None:
        raise GatewayRejectedError("invalid CID")
    try:
        parsed = make_cid(value)
    except (ValueError, TypeError, KeyError, IndexError, OverflowError):
        raise GatewayRejectedError("invalid CID") from None
    if not isinstance(parsed, CIDv1) or parsed.codec not in {"raw", "json", "dag-json"}:
        raise GatewayRejectedError("unsupported CID version or codec")
    if len(parsed.multihash) != 34 or parsed.multihash[:2] != b"\x12\x20":
        raise GatewayRejectedError("CID requires a full sha2-256 digest")
    return parsed


class GatewayClient:
    """Own one async session; use async-with or aclose. No retries or redirects.

    Supports single-block CIDv1 raw, json and dag-json with sha2-256. This verifies
    byte integrity, not JSON schema, DAG links, UnixFS files or provenance claims.
    """

    def __init__(
        self,
        settings: GatewaySettings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        url = None
        try:
            url = httpx.URL(settings.url)
        except (httpx.InvalidURL, ValueError):
            pass
        if (
            url is None
            or not url.host
            or url.scheme not in {"http", "https"}
            or url.userinfo
            or url.query
            or url.fragment
            or url.path not in {"", "/"}
            or any(character.isspace() or ord(character) < 32 for character in settings.url)
        ):
            raise GatewayRejectedError("invalid gateway origin")
        self._settings = settings
        self._http = httpx.AsyncClient(
            base_url=url,
            headers={"Accept": "application/vnd.ipld.raw", "Accept-Encoding": "identity"},
            timeout=httpx.Timeout(
                settings.timeout_seconds, connect=min(5, settings.timeout_seconds)
            ),
            follow_redirects=False,
            trust_env=False,
            transport=transport,
        )

    async def __aenter__(self) -> GatewayClient:
        if self._http.is_closed:
            raise GatewayUnavailableError("gateway client is closed")
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._http.aclose()

    async def fetch(self, cid: str) -> bytes:
        parsed = _parse_cid(cid)
        if self._http.is_closed:
            raise GatewayUnavailableError("gateway client is closed")
        reference = parsed.encode("base32").decode("ascii")
        try:
            body = await asyncio.wait_for(
                self._fetch_block(reference), timeout=self._settings.timeout_seconds
            )
        except (httpx.HTTPError, TimeoutError):
            raise GatewayUnavailableError("gateway request failed") from None
        if hashlib.sha256(body).digest() != parsed.multihash[2:]:
            raise GatewayMismatchError("gateway content does not match CID")
        return bytes(body)

    async def _fetch_block(self, reference: str) -> bytearray:
        async with self._http.stream(
            "GET", f"/ipfs/{reference}", params={"format": "raw"}
        ) as response:
            if (
                response.status_code != 200
                or response.headers.get("Content-Encoding", "identity").lower() != "identity"
                or response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
                != "application/vnd.ipld.raw"
            ):
                raise GatewayUnavailableError("gateway did not return a raw block")
            length = response.headers.get("Content-Length")
            if length is not None and (
                not length.isascii()
                or not length.isdecimal()
                or len(length) > 20
                or int(length) > self._settings.max_response_bytes
            ):
                raise GatewayUnavailableError("invalid or excessive gateway response size")
            body = bytearray()
            # Raw iteration avoids allocating a decompressed body before the size check.
            async for chunk in response.aiter_raw():
                if len(body) + len(chunk) > self._settings.max_response_bytes:
                    raise GatewayUnavailableError("gateway response exceeds size limit")
                body.extend(chunk)
            if length is not None and len(body) != int(length):
                raise GatewayUnavailableError("incomplete gateway response")
        return body
