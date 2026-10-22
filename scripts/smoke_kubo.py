"""Exercise the Compose Kubo service offline using disposable resources and public data."""

from __future__ import annotations

import argparse
import json
import os
import secrets
import subprocess
import sys
import tempfile
import time
import urllib.error
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


def require_rpc_denied(
    command: list[str],
    data: bytes | None = None,
    env: dict[str, str] | None = None,
) -> None:
    """Distinguish native authorization denial from connection or CLI failures."""
    result = subprocess.run(command, input=data, env=env, capture_output=True, timeout=15)
    require(
        result.returncode != 0 and b"Kubo RPC Access Denied" in result.stdout + result.stderr,
        "Expected native RPC authorization denial",
    )


def require_read_only_gateway(url: str) -> None:
    for method in ("POST", "PUT", "DELETE"):
        request = urllib.request.Request(url, data=b"must-not-write", method=method)
        try:
            with urllib.request.urlopen(request, timeout=15):
                raise RuntimeError(f"Gateway unexpectedly accepted {method}")
        except urllib.error.HTTPError as error:
            with error:
                require(error.code in (404, 405), f"Unexpected gateway status for {method}")


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
    secret = secrets.token_urlsafe(32)
    service.setdefault("environment", {})["KUBO_RPC_SECRET"] = secret
    service["command"] = ["daemon", "--offline", "--migrate=false"]
    for port in service["ports"]:
        port.pop("published", None)
    # Omit normalized resource names so cleanup cannot touch an existing stack.
    manifest = {
        "services": {"kubo": service},
        "volumes": {"kubo_data": {"driver": "local"}},
        "networks": {"content_network": {"driver": "bridge"}},
    }
    project = f"qmesh-kubo-smoke-{uuid.uuid4().hex[:12]}"
    with tempfile.TemporaryDirectory(prefix="qmesh-kubo-") as directory:
        config = Path(directory) / "compose.json"
        config.write_text(json.dumps(manifest), encoding="utf-8")
        config.chmod(0o600)
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
        execute = [*compose, "exec", "-T", "kubo"]
        cli = [*execute, "sh", "/opt/qmesh/kubo-rpc.sh"]
        anonymous = [*execute, "ipfs", RPC]
        try:
            print(
                "Starting isolated offline Kubo (no backend, Caddy or public peers)...", flush=True
            )
            run([*compose, "up", "-d", "--wait", "--wait-timeout", "90", "kubo"])
            # This is our disposable node only. Inspect in memory; never print/store its config.
            settings = json.loads(run([*execute, "cat", "/data/ipfs/config"]))
            require(settings["Discovery"]["MDNS"]["Enabled"] is False, "mDNS must be disabled")
            require(settings["Swarm"]["DisableNatPortMap"] is True, "NAT mapping must be disabled")
            require(settings["Gateway"]["NoFetch"] is True, "Gateway must serve local content only")
            require(settings["Gateway"]["NoDNSLink"] is True, "DNSLink must be disabled")
            require(
                settings["Gateway"]["ExposeRoutingAPI"] is False, "Routing API must be disabled"
            )
            require(settings["Swarm"]["ConnMgr"]["HighWater"] == 96, "Connection limit missing")
            require(
                settings["Swarm"]["ResourceMgr"]["MaxFileDescriptors"] == 1024,
                "Swarm FD limit missing",
            )
            require(
                settings["API"]["Authorizations"]["backend"]["AuthSecret"] == f"bearer:{secret}",
                "RPC authorization was not configured",
            )
            del settings
            require_rpc_denied([*anonymous, "id"])
            require_rpc_denied([*anonymous, "--api-auth=bearer:invalid-fixture", "id"])
            require(bool(json.loads(run([*cli, "id"])).get("ID")), "Authorized RPC failed")
            require_rpc_denied([*anonymous, "add", "-Q"], data=b"must-not-publish")
            require_rpc_denied([*cli, "config", "show"])
            require_rpc_denied([*cli, "config", "--json", "Gateway.NoFetch", "false"])
            version = subprocess.run(
                [*execute, "wget", "-SqO-", "--post-data=", "http://127.0.0.1:5001/api/v0/version"],
                capture_output=True,
                timeout=15,
            )
            require(
                version.returncode != 0 and b"HTTP/1.1 403" in version.stderr,
                "Anonymous version RPC must also require authentication",
            )
            print(
                "Healthy; anonymous/wrong-token/admin RPC denied; authorized RPC works.", flush=True
            )
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
            require_read_only_gateway(f"http://127.0.0.1:{gateway}/ipfs/{cid}")
            print(f"Retrieved CID: {checked}; bytes match; gateway writes rejected.", flush=True)
            run(
                [*compose, "up", "-d", "--force-recreate", "--wait", "--wait-timeout", "90", "kubo"]
            )
            recreated = run([*compose, "ps", "-q", "kubo"]).decode().strip()
            require(recreated != container, "Expected the container to be recreated")
            require(run([*cli, "cat", cid]) == FIXTURE, "Content did not survive recreation")
            run([*cli, "pin", "ls", "--type=recursive", cid])
            require_rpc_denied([*anonymous, "id"])
            old_secret = secret
            secret = secrets.token_urlsafe(32)
            service["environment"]["KUBO_RPC_SECRET"] = secret
            config.write_text(json.dumps(manifest), encoding="utf-8")
            run(
                [*compose, "up", "-d", "--force-recreate", "--wait", "--wait-timeout", "90", "kubo"]
            )
            require(bool(json.loads(run([*cli, "id"])).get("ID")), "Rotated secret failed")
            require_rpc_denied(
                [
                    *compose,
                    "exec",
                    "-T",
                    "-e",
                    "KUBO_RPC_SECRET",
                    "kubo",
                    "sh",
                    "/opt/qmesh/kubo-rpc.sh",
                    "id",
                ],
                env={**os.environ, "KUBO_RPC_SECRET": old_secret},
            )
            require(run([*cli, "cat", cid]) == FIXTURE, "Rotation lost the content")
            container = run([*compose, "ps", "-q", "kubo"]).decode().strip()
            logs = subprocess.run(
                ["docker", "logs", container], check=True, capture_output=True, timeout=15
            )
            require(
                all(
                    value.encode() not in logs.stdout + logs.stderr
                    for value in (secret, old_secret)
                ),
                "Secret leaked in Kubo logs",
            )
            health = run(["docker", "inspect", "--format", "{{json .State.Health.Log}}", container])
            require(
                all(value.encode() not in health for value in (secret, old_secret)),
                "Secret leaked in healthcheck logs",
            )
            run([*compose, "stop", "kubo"])
            missing = subprocess.run(
                [
                    *compose,
                    "run",
                    "--rm",
                    "--no-deps",
                    "-e",
                    "KUBO_RPC_SECRET=",
                    "kubo",
                    "daemon",
                    "--offline",
                    "--migrate=false",
                ],
                capture_output=True,
                timeout=30,
            )
            require(
                missing.returncode != 0 and b"requires a 32-128" in missing.stderr,
                "Missing secret did not prevent startup",
            )
            print(
                "PASS: data/auth persist; rotation revokes old token; missing secret fails closed.",
                flush=True,
            )
        finally:
            cleanup(compose, project, primary_failed=sys.exc_info()[0] is not None)


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError) as error:
        raise SystemExit(f"FAIL: {error}") from None
