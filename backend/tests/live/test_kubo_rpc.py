"""Opt-in check against a disposable Kubo v0.43.1 node on a private network."""

from __future__ import annotations

import base64
import hashlib
import os
from uuid import uuid4

import pytest

from quantum_backend_v2.config import AppSettings
from quantum_backend_v2.content.kubo import KuboClient

pytestmark = [
    pytest.mark.anyio,
    pytest.mark.live_kubo,
    pytest.mark.skipif(
        os.environ.get("QB2_KUBO_LIVE_TEST") != "1", reason="Disposable Kubo test not enabled"
    ),
]


def _raw_car(payload: bytes) -> tuple[str, bytes]:
    """Build one tiny CARv1 fixture: raw/SHA256 CID, DAG-CBOR header, one block."""
    cid = b"\x01\x55\x12\x20" + hashlib.sha256(payload).digest()
    header = b"\xa2\x65roots\x81\xd8\x2a\x58\x25\x00" + cid + b"\x67version\x01"
    block = cid + payload
    assert len(header) < 128 and len(block) < 128
    encoded = "b" + base64.b32encode(cid).decode().lower().rstrip("=")
    return encoded, bytes([len(header)]) + header + bytes([len(block)]) + block


async def test_real_add_pin_unpin_listing_car_and_block_stat() -> None:
    settings = AppSettings.from_env(
        {
            "KUBO_RPC_URL": os.environ.get("KUBO_RPC_URL", "http://kubo:5001"),
            "KUBO_RPC_SECRET": os.environ.get("KUBO_RPC_SECRET", ""),
        }
    )
    payload = b"public harmless Kubo client fixture " + uuid4().hex.encode()
    car_cid, car = _raw_car(b"public CAR fixture " + uuid4().hex.encode())
    owned: set[str] = set()
    async with KuboClient(settings.kubo) as client:
        try:
            added = await client.add(payload)
            owned.add(added.cid)
            assert added.size_bytes == len(payload)
            assert (await client.pin_add(added.cid)).pins == (added.cid,)
            assert (await client.pin_ls(added.cid)).pins[added.cid].type == "recursive"
            assert (await client.block_stat(added.cid)).size_bytes == len(payload)
            await client.pin_rm(added.cid)
            owned.remove(added.cid)
            assert added.cid not in (await client.pin_ls()).pins
            imported = await client.dag_import(car)
            owned.update(imported.pinned_roots)
            assert imported.pinned_roots == (car_cid,)
            assert imported.block_count == 1
            assert (await client.block_stat(car_cid)).size_bytes == imported.block_bytes
            await client.pin_rm(car_cid)
            owned.remove(car_cid)
            unpinned = await client.dag_import(car, pin_roots=False)
            assert unpinned.pinned_roots == ()
            assert car_cid not in (await client.pin_ls()).pins
        finally:
            # No GC or deletion of unrelated content; only this test's unique pins.
            for cid in owned:
                await client.pin_rm(cid)
