"""Exercise the Compose Kubo service offline using disposable resources and public data."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import time
import urllib.request
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RPC = "--api=/ip4/127.0.0.1/tcp/5001"
FIXTURE = b"QMeshPy Kubo smoke test: harmless public fixture.\n"


def run(command: list[str], data: bytes | None = None) -> bytes:
    """Capture commands without printing configuration or inherited credentials."""
    operation = next(
        (arg for arg in command[2:] if arg in {"config", "up", "exec", "ps", "down"}),
        "operation",
    )
    label = (
        f"docker compose {operation}" if command[:2] == ["docker", "compose"] else "docker inspect"
    )
    try:
        return subprocess.run(
            command,
            input=data,
            capture_output=True,
            check=True,
            timeout=120,
        ).stdout
    except subprocess.CalledProcessError as error:
        raise RuntimeError(
            f"{label} failed (exit {error.returncode}). Check Docker/Compose and service health; "
            "captured output is withheld to avoid exposing credentials."
        ) from None
    except subprocess.TimeoutExpired:
        raise RuntimeError(
            f"{label} timed out after 120 seconds. Check Docker and service health."
        ) from None


def cleanup(compose: list[str], project: str, primary_failed: bool) -> None:
    """Report cleanup failure without replacing an existing failure or interruption."""
    try:
        run([*compose, "down", "--volumes", "--remove-orphans"])
    except (RuntimeError, OSError, subprocess.SubprocessError):
        if not primary_failed:
            raise
        print(
            f"WARNING: cleanup also failed for {project}; inspect resources labelled "
            f"com.docker.compose.project={project}.",
            file=sys.stderr,
        )
    else:
        print("Disposed of this smoke test's containers, network and volume.", flush=True)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def gateway_port(bindings: object) -> str:
    """Check every published binding; duplicate loopback entries are harmless."""
    message = f"Gateway must bind only to IPv4 loopback on a valid port; observed: {bindings!r}"
    if not isinstance(bindings, list) or not bindings:
        raise RuntimeError(message)
    ports: list[str] = []
    for binding in bindings:
        if not isinstance(binding, dict) or binding.get("HostIp") != "127.0.0.1":
            raise RuntimeError(message)
        port = binding.get("HostPort")
        if not isinstance(port, str) or not port.isdecimal() or not 0 < int(port) <= 65535:
            raise RuntimeError(message)
        ports.append(port)
    return ports[0]


def published_gateway(container: str) -> str:
    """Wait briefly for port metadata, never retrying an unsafe published binding."""
    deadline = time.monotonic() + 10
    while True:
        ports = json.loads(
            run(
                [
                    "docker",
                    "inspect",
                    "--format",
                    "{{json .NetworkSettings.Ports}}",
                    container,
                ]
            )
        )
        require(isinstance(ports, dict), "Docker returned invalid port metadata")
        require(not ports.get("5001/tcp"), "RPC port must not have a host binding")
        bindings = ports.get("8080/tcp")
        # Daemon health can precede Docker Desktop's published-port metadata.
        if bindings not in (None, []) or time.monotonic() >= deadline:
            return gateway_port(bindings)
        time.sleep(0.25)


def main() -> None:
    argparse.ArgumentParser(description=__doc__).parse_args()
    # No interpolation or project .env loading: discard every non-Kubo service.
    model: dict[str, Any] = json.loads(
        run(
            [
                "docker",
                "compose",
                "--env-file",
                "/dev/null",
                "-f",
                str(ROOT / "docker-compose.yaml"),
                "config",
                "--no-interpolate",
                "--format",
                "json",
            ]
        )
    )
    service = model["services"]["kubo"]
    service["command"] = ["daemon", "--offline", "--migrate=false"]
    for port in service["ports"]:
        port.pop("published", None)
    # Omit normalized resource names so cleanup cannot touch an existing stack.
    manifest = {
        "services": {"kubo": service},
        "volumes": {"kubo_data": {"driver": "local"}},
        "networks": {"backend_network": {"driver": "bridge"}},
    }
    project = f"qmesh-kubo-smoke-{uuid.uuid4().hex[:12]}"
    with tempfile.TemporaryDirectory(prefix="qmesh-kubo-") as directory:
        config = Path(directory) / "compose.json"
        config.write_text(json.dumps(manifest), encoding="utf-8")
        compose = [
            "docker",
            "compose",
            "--env-file",
            "/dev/null",
            "-p",
            project,
            "-f",
            str(config),
        ]
        cli = [*compose, "exec", "-T", "kubo", "ipfs", RPC]
        try:
            print(
                "Starting isolated offline Kubo (no backend, Caddy or public peers)...", flush=True
            )
            run([*compose, "up", "-d", "--wait", "--wait-timeout", "90", "kubo"])
            require(
                run([*cli, "config", "Discovery.MDNS.Enabled"]).strip() == b"false",
                "server profile did not disable mDNS",
            )
            require(
                run([*cli, "config", "Swarm.DisableNatPortMap"]).strip() == b"true",
                "server profile did not disable NAT port mapping",
            )
            print("Healthy; server profile verified.", flush=True)
            container = run([*compose, "ps", "-q", "kubo"]).decode().strip()
            gateway = published_gateway(container)
            print("RPC is unpublished; gateway is loopback-only.", flush=True)
            cid = (
                run([*cli, "add", "-Q", "--cid-version=1", "--pin=true"], FIXTURE).decode().strip()
            )
            require(bool(cid) and "\n" not in cid, "Expected one CID")
            print(f"Added CID: {cid}", flush=True)
            content = run([*cli, "cat", cid])
            require(content == FIXTURE, "Retrieved bytes differ from the fixture")
            checked = (
                run([*cli, "add", "-Q", "--cid-version=1", "--only-hash"], content).decode().strip()
            )
            require(checked == cid, "Recomputed CID differs")
            with urllib.request.urlopen(
                f"http://127.0.0.1:{gateway}/ipfs/{cid}",
                timeout=15,
            ) as response:
                require(response.read() == FIXTURE, "Gateway returned different content")
            print(f"Retrieved CID: {checked}; RPC and gateway bytes match.", flush=True)
            run(
                [*compose, "up", "-d", "--force-recreate", "--wait", "--wait-timeout", "90", "kubo"]
            )
            recreated = run([*compose, "ps", "-q", "kubo"]).decode().strip()
            require(recreated != container, "Expected the container to be recreated")
            require(run([*cli, "cat", cid]) == FIXTURE, "Content did not survive recreation")
            run([*cli, "pin", "ls", "--type=recursive", cid])
            print("PASS: content and pin survive container recreation.", flush=True)
        finally:
            cleanup(compose, project, primary_failed=sys.exc_info()[0] is not None)


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError) as error:
        raise SystemExit(f"FAIL: {error}") from None
