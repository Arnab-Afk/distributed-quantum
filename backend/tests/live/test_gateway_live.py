"""Opt-in end-to-end checks with a disposable, offline Kubo node."""

import hashlib
import os
import subprocess
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from uuid import uuid4

import pytest
import yaml
from cid import make_cid

from quantum_backend_v2.config import GatewaySettings
from quantum_backend_v2.content.gateway import (
    GatewayClient,
    GatewayMismatchError,
    GatewayUnavailableError,
)

pytestmark = [
    pytest.mark.anyio,
    pytest.mark.live_kubo,
    pytest.mark.skipif(
        os.environ.get("QB2_GATEWAY_LIVE_TEST") != "1", reason="Disposable gateway test not enabled"
    ),
]
PAYLOAD = b'{"fixture":"public gateway verification"}'


def docker(*args, input=None):
    return (
        subprocess.run(["docker", *args], input=input, capture_output=True, check=True, timeout=60)
        .stdout.decode()
        .strip()
    )


@pytest.fixture(scope="module")
def kubo():
    compose = yaml.safe_load(
        (Path(__file__).resolve().parents[3] / "docker-compose.yaml").read_text()
    )
    image = compose["services"]["kubo"]["image"]
    name = "qmesh-gateway-test-" + uuid4().hex[:12]
    docker("network", "create", name)
    try:
        docker(
            "run",
            "--detach",
            "--rm",
            "--name",
            name,
            "--network",
            name,
            "--publish",
            "127.0.0.1::8080",
            "--tmpfs",
            "/data/ipfs:rw,mode=1777",
            "--entrypoint",
            "sh",
            image,
            "-ec",
            "ipfs init --profile=test >/dev/null; "
            "ipfs config Addresses.Gateway /ip4/0.0.0.0/tcp/8080; "
            "exec ipfs daemon --offline",
        )
        deadline = time.monotonic() + 30
        while "Daemon is ready" not in docker("logs", name):
            if time.monotonic() >= deadline:
                pytest.fail("disposable Kubo did not become ready")
            time.sleep(0.1)
        binding = docker("port", name, "8080/tcp")
        assert binding.startswith("127.0.0.1:")
        yield name, "http://" + binding
    finally:
        subprocess.run(["docker", "rm", "--force", name], capture_output=True, timeout=30)
        docker("network", "rm", name)


def put_block(kubo, codec):
    name, _ = kubo
    return docker(
        "exec",
        "--interactive",
        name,
        "ipfs",
        "block",
        "put",
        "--cid-codec=" + codec,
        "--mhtype=sha2-256",
        input=PAYLOAD,
    )


@pytest.mark.parametrize("codec", ["raw", "json", "dag-json"])
async def test_kubo_block_round_trip(kubo, codec):
    reference = put_block(kubo, codec)
    async with GatewayClient(GatewaySettings(url=kubo[1])) as client:
        assert await client.fetch(reference) == PAYLOAD
        assert await client.fetch(reference) == PAYLOAD


async def test_kubo_response_exceeding_limit_is_unavailable(kubo):
    reference = put_block(kubo, "raw")
    async with GatewayClient(GatewaySettings(url=kubo[1], max_response_bytes=8)) as client:
        with pytest.raises(GatewayUnavailableError):
            await client.fetch(reference)


async def test_missing_block_on_offline_gateway_is_unavailable(kubo):
    digest = hashlib.sha256(uuid4().bytes).digest()
    reference = make_cid(1, "raw", b"\x12\x20" + digest).encode("base32").decode()
    async with GatewayClient(GatewaySettings(url=kubo[1], timeout_seconds=2)) as client:
        with pytest.raises(GatewayUnavailableError):
            await client.fetch(reference)


async def test_modified_gateway_bytes_are_rejected_over_http(kubo):
    reference = put_block(kubo, "raw")

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 - HTTP server callback name
            body = PAYLOAD + b"tampered"
            self.send_response(200)
            self.send_header("Content-Type", "application/vnd.ipld.raw")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        origin = f"http://127.0.0.1:{server.server_port}"
        async with GatewayClient(GatewaySettings(url=origin)) as client:
            with pytest.raises(GatewayMismatchError):
                await client.fetch(reference)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
