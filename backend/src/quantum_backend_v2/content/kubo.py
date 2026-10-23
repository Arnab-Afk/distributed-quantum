"""Typed, bounded RPC access to Kubo; no execution/startup integration."""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Callable
from types import TracebackType
from typing import Annotated, BinaryIO, Literal, TypeVar

import httpx
from pydantic import BaseModel, ConfigDict, Field, field_validator

from quantum_backend_v2.config import KuboSettings
from quantum_backend_v2.content._transport import KuboRPCTransport

_CID = Annotated[str, Field(min_length=1, max_length=512)]
_Count = Annotated[int, Field(ge=0, strict=True)]
_ResultT = TypeVar("_ResultT", bound=BaseModel)


class KuboError(Exception):
    """Sanitized failure; a mutation may already have been applied. Never retry blindly."""

    category = "error"

    def __init__(self, operation: str, status_code: int | None = None) -> None:
        self.operation = operation
        self.status_code = status_code
        status = f" (HTTP {status_code})" if status_code is not None else ""
        super().__init__(f"Kubo {operation} {self.category}{status}")


class KuboUnavailableError(KuboError):
    """No reliable successful response: timeout, transport, service or protocol failure."""

    category = "unavailable"


class KuboRejectedError(KuboError):
    """Configuration/request rejected, or an explicit RPC operation/pin error."""

    category = "rejected"


class _Result(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        populate_by_name=True,
        hide_input_in_errors=True,
    )


class AddResult(_Result):
    """CID and reported DAG size, which may differ from the original payload length."""

    cid: _CID = Field(alias="Hash")
    size_bytes: _Count = Field(alias="Size")
    name: str = Field(default="", alias="Name", repr=False)
    bytes_processed: _Count = Field(default=0, alias="Bytes", repr=False)
    mode: str | None = Field(default=None, alias="Mode", repr=False)
    mtime: int | None = Field(default=None, alias="Mtime", strict=True, repr=False)
    mtime_nsecs: _Count | None = Field(default=None, alias="MtimeNsecs", repr=False)

    @field_validator("size_bytes", mode="before")
    @classmethod
    def _size_from_decimal_string(cls, value: object) -> object:
        # Kubo encodes add.Size as a decimal string, unlike block/stat.Size.
        if isinstance(value, str) and value.isascii() and value.isdecimal():
            return int(value)
        return value


class PinResult(_Result):
    """Acknowledged pin changes; unpinning does not immediately delete blocks."""

    pins: tuple[_CID, ...] = Field(alias="Pins", min_length=1)


class PinInfo(_Result):
    """Pin type/name as reported by Kubo."""

    type: Literal["recursive", "direct", "indirect"] = Field(alias="Type")
    name: str = Field(default="", alias="Name")


class PinListResult(_Result):
    """Pin metadata; an empty node can omit the Keys field entirely."""

    pins: dict[_CID, PinInfo] = Field(default_factory=dict, alias="Keys")


class BlockStat(_Result):
    """Reported block CID/size; not independent verification of its bytes."""

    cid: _CID = Field(alias="Key")
    size_bytes: _Count = Field(alias="Size")


class ImportResult(_Result):
    """Imported block statistics and roots pinned by this call, not all CAR header roots."""

    pinned_roots: tuple[_CID, ...]
    block_count: _Count
    block_bytes: _Count


class _Link(_Result):
    cid: _CID = Field(alias="/")


class _ImportRoot(_Result):
    cid: _Link = Field(alias="Cid")
    pin_error: str = Field(default="", alias="PinErrorMsg", repr=False)


class _ImportStats(_Result):
    block_count: _Count = Field(alias="BlockCount")
    block_bytes: _Count = Field(alias="BlockBytesCount")


class _ImportEvent(_Result):
    root: _ImportRoot | None = Field(default=None, alias="Root")
    stats: _ImportStats | None = Field(default=None, alias="Stats")


def _single(records: list[object], model: type[_ResultT]) -> _ResultT:
    if len(records) != 1:
        raise ValueError("Expected a single RPC result")
    return model.model_validate(records[0])


# go-ipfs-cmds v0.16.1 ErrorType values. Kubo sends ErrClient as HTTP 400 and every
# other command error as HTTP 500 with a JSON {"Message", "Code", "Type": "error"} body.
_DEFINITE_ERROR_CODES = frozenset({0, 1, 4})  # ErrNormal, ErrClient, ErrForbidden
# Kubo reports its own internal timeouts as ErrNormal; those outcomes are not definite.
_TRANSIENT_ERROR_TEXT = (b"context deadline exceeded", b"context canceled")
_ERROR_BODY_LIMIT = 64 * 1024


async def _classify_command_error(response: httpx.Response, operation: str) -> KuboError:
    """Return rejected only for a well-formed, definite Kubo command error.

    The message is inspected but never kept, so remote error text cannot reach logs.
    Proxies, crashes, rate limits and malformed bodies remain unavailable.
    """
    body = bytearray()
    try:
        async for chunk in response.aiter_bytes():
            body.extend(chunk)
            if len(body) > _ERROR_BODY_LIMIT:
                return KuboUnavailableError(operation, 500)
        record = json.loads(body, object_pairs_hook=_unique_object)
    except (httpx.HTTPError, ValueError):
        return KuboUnavailableError(operation, 500)
    if (
        isinstance(record, dict)
        and record.get("Type") == "error"
        and type(record.get("Code")) is int
        and record["Code"] in _DEFINITE_ERROR_CODES
        and isinstance(record.get("Message"), str)
        and not any(text in record["Message"].encode() for text in _TRANSIENT_ERROR_TEXT)
    ):
        return KuboRejectedError(operation, 500)
    return KuboUnavailableError(operation, 500)


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON field")
        result[key] = value
    return result


class KuboClient:
    """Own one async session; close with async-with or aclose. No automatic retries.

    Binary input streams remain caller-owned and must be regular, nonblocking
    files. Context cancellation propagates; unavailable writes have uncertain
    outcomes, even when the caller did not receive a successful response.
    """

    def __init__(
        self,
        settings: KuboSettings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        token = settings.rpc_secret.get_secret_value() if settings.rpc_secret else ""
        url: httpx.URL | None = None
        try:
            url = httpx.URL(settings.rpc_url)
        except (httpx.InvalidURL, ValueError):
            pass
        if (
            re.fullmatch(r"[A-Za-z0-9_-]{32,128}", token) is None
            or url is None
            or not url.host
            or url.scheme not in {"http", "https"}
            or url.username
            or url.password
            or url.query
            or url.fragment
            or url.path not in {"", "/", "/api/v0", "/api/v0/"}
            or token in settings.rpc_url
        ):
            raise KuboRejectedError("configuration")
        self._token = token
        self._settings = settings
        self._http = httpx.AsyncClient(
            base_url=url.copy_with(path="/api/v0/"),
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
                "Accept-Encoding": "identity",
            },
            timeout=httpx.Timeout(
                settings.timeout_seconds, connect=min(5, settings.timeout_seconds)
            ),
            follow_redirects=False,
            trust_env=False,
            transport=transport if transport is not None else KuboRPCTransport(),
        )

    async def __aenter__(self) -> KuboClient:
        if self._http.is_closed:
            raise KuboUnavailableError("session")
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        try:
            await self.aclose()
        except KuboError:
            # Cleanup must not replace the operation's failure or cancellation.
            if exc is None:
                raise

    async def aclose(self) -> None:
        """Release the owned HTTP session without closing caller upload files."""
        try:
            await asyncio.wait_for(self._http.aclose(), self._settings.timeout_seconds)
        except (asyncio.TimeoutError, httpx.HTTPError, OSError, RuntimeError):
            raise KuboUnavailableError("close") from None

    def _cid(self, cid: str, operation: str) -> str:
        if (
            not isinstance(cid, str)
            or not cid
            or len(cid) > 512
            or any(c.isspace() or ord(c) < 32 for c in cid)
            or self._token in cid
        ):
            raise KuboRejectedError(operation)
        return cid

    async def add(self, data: bytes | BinaryIO, *, pin: bool = True) -> AddResult:
        """Upload one file using CIDv1; optionally retain its DAG with a recursive pin."""
        return await self._perform(
            "add",
            lambda records: _single(records, AddResult),
            data=data,
            params={
                "pin": str(pin).lower(),
                "cid-version": "1",
                "progress": "false",
                "wrap-with-directory": "false",
            },
        )

    async def pin_add(self, cid: str, *, recursive: bool = True) -> PinResult:
        """Pin an existing or retrievable CID."""
        return await self._perform(
            "pin/add",
            lambda records: _single(records, PinResult),
            params={
                "arg": self._cid(cid, "pin/add"),
                "recursive": str(recursive).lower(),
                "progress": "false",
            },
        )

    async def pin_rm(self, cid: str, *, recursive: bool = True) -> PinResult:
        """Remove a pin; garbage collection and other references determine deletion."""
        return await self._perform(
            "pin/rm",
            lambda records: _single(records, PinResult),
            params={"arg": self._cid(cid, "pin/rm"), "recursive": str(recursive).lower()},
        )

    async def pin_ls(self, cid: str | None = None) -> PinListResult:
        """List pin metadata, optionally restricted to a CID."""
        params = {"stream": "false", "type": "all"}
        if cid is not None:
            params["arg"] = self._cid(cid, "pin/ls")
        return await self._perform(
            "pin/ls", lambda records: _single(records, PinListResult), params=params
        )

    async def block_stat(self, cid: str) -> BlockStat:
        """Inspect a block without downloading its bytes."""
        return await self._perform(
            "block/stat",
            lambda records: _single(records, BlockStat),
            params={"arg": self._cid(cid, "block/stat")},
        )

    async def dag_import(self, data: bytes | BinaryIO, *, pin_roots: bool = True) -> ImportResult:
        """Import a CAR; when pin_roots=False, Kubo does not report its header roots."""

        def parse(records: list[object]) -> ImportResult:
            roots: list[str] = []
            seen: set[str] = set()
            stats: _ImportStats | None = None
            for record in records:
                event = _ImportEvent.model_validate(record)
                if (event.root is None) == (event.stats is None) or stats is not None:
                    raise ValueError("Invalid CAR result sequence")
                if event.root is not None:
                    if event.root.pin_error:
                        raise KuboRejectedError("dag/import")
                    if not pin_roots or event.root.cid.cid in seen:
                        raise ValueError("Unexpected CAR root")
                    seen.add(event.root.cid.cid)
                    roots.append(event.root.cid.cid)
                else:
                    stats = event.stats
            if stats is None:
                raise ValueError("Missing CAR statistics")
            return ImportResult(
                pinned_roots=tuple(roots),
                block_count=stats.block_count,
                block_bytes=stats.block_bytes,
            )

        return await self._perform(
            "dag/import",
            parse,
            data=data,
            filename="import.car",
            media_type="application/vnd.ipld.car",
            params={"pin-roots": str(pin_roots).lower(), "stats": "true"},
        )

    async def _perform(
        self,
        operation: str,
        parse: Callable[[list[object]], _ResultT],
        *,
        params: dict[str, str] | None = None,
        data: bytes | BinaryIO | None = None,
        filename: str = "content",
        media_type: str = "application/octet-stream",
    ) -> _ResultT:
        if self._http.is_closed:
            raise KuboUnavailableError(operation)

        async def run() -> _ResultT:
            records = await self._receive(operation, params, data, filename, media_type)
            return parse(records)

        try:
            return await asyncio.wait_for(run(), timeout=self._settings.timeout_seconds)
        except (asyncio.TimeoutError, httpx.HTTPError, OSError, ValueError, RuntimeError):
            raise KuboUnavailableError(operation) from None

    async def _receive(
        self,
        operation: str,
        params: dict[str, str] | None,
        data: bytes | BinaryIO | None,
        filename: str,
        media_type: str,
    ) -> list[object]:
        files = {"file": (filename, data, media_type)} if data is not None else None
        async with self._http.stream(
            "POST", operation, params={"encoding": "json", **(params or {})}, files=files
        ) as response:
            status = response.status_code
            if status == 500:
                raise await _classify_command_error(response, operation)
            if status != 200:
                error = (
                    KuboUnavailableError
                    if status > 500 or status in {408, 429} or status < 300
                    else KuboRejectedError
                )
                raise error(operation, status)
            if (
                response.headers.get("X-Stream-Error")
                or response.headers.get("Content-Encoding", "identity").lower() != "identity"
            ):
                raise KuboUnavailableError(operation)
            maximum = self._settings.max_response_bytes
            if int(response.headers.get("Content-Length", "0")) > maximum:
                raise KuboUnavailableError(operation)
            body = bytearray()
            async for chunk in response.aiter_bytes():
                if len(body) + len(chunk) > maximum:
                    raise KuboUnavailableError(operation)
                body.extend(chunk)
            # Consume through EOF first: the default transport checks late error trailers.
            try:
                records = [json.loads(body, object_pairs_hook=_unique_object)]
            except json.JSONDecodeError:
                records = [
                    json.loads(line, object_pairs_hook=_unique_object)
                    for line in body.splitlines()
                    if line.strip()
                ]
            if not records or not all(isinstance(record, dict) for record in records):
                raise ValueError("Expected RPC JSON objects")
            for record in records:
                if record.get("Type") == "error" or ("Message" in record and "Code" in record):
                    raise KuboRejectedError(operation)
            return records
