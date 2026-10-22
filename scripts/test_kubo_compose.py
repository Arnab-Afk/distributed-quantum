"""Check the content-node deployment contract without starting any services."""

from __future__ import annotations

import contextlib
import io
import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from typing import Any, ClassVar
from unittest.mock import patch

import smoke_kubo

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("docker"), "Docker Compose CLI is required")
class KuboComposeTests(unittest.TestCase):
    model: ClassVar[dict[str, Any]]
    kubo: ClassVar[dict[str, Any]]

    @classmethod
    def setUpClass(cls) -> None:
        result = subprocess.run(
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
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=15,
        )
        cls.model = json.loads(result.stdout)
        cls.kubo = cls.model["services"].get("kubo", {})

    def test_release_and_digest_are_pinned(self) -> None:
        self.assertRegex(
            self.kubo.get("image", ""),
            r"^ipfs/kubo:v\d+\.\d+\.\d+@sha256:[0-9a-f]{64}$",
        )

    def test_server_profile_is_applied_at_initialization(self) -> None:
        self.assertEqual(self.kubo.get("environment", {}).get("IPFS_PROFILE"), "server")

    def test_repository_uses_a_named_volume(self) -> None:
        mounts = self.kubo.get("volumes", [])
        self.assertTrue(
            any(
                m.get("type") == "volume"
                and m.get("source") in self.model["volumes"]
                and m.get("target") == "/data/ipfs"
                for m in mounts
            )
        )

    def test_rpc_is_not_published_or_host_networked(self) -> None:
        self.assertTrue(self.kubo)
        self.assertNotIn("network_mode", self.kubo)
        self.assertIn("content_network", self.kubo.get("networks", {}))
        self.assertIn("content_network", self.model["services"]["backend"]["networks"])
        self.assertNotIn("content_network", self.model["services"]["caddy"]["networks"])
        self.assertFalse(any(p["target"] == 5001 for p in self.kubo.get("ports", [])))
        self.assertNotIn("kubo:5001", (ROOT / "deploy/Caddyfile").read_text())

    def test_gateway_is_loopback_only(self) -> None:
        ports = [p for p in self.kubo.get("ports", []) if p["target"] == 8080]
        self.assertEqual(len(ports), 1)
        self.assertEqual(ports[0].get("host_ip"), "127.0.0.1")
        self.assertEqual(ports[0].get("published"), "${KUBO_GATEWAY_PORT:-8080}")

    def test_swarm_supports_tcp_and_udp(self) -> None:
        protocols = {p["protocol"] for p in self.kubo.get("ports", []) if p["target"] == 4001}
        self.assertEqual(protocols, {"tcp", "udp"})

    def test_healthcheck_contacts_daemon_not_just_local_repo(self) -> None:
        self.assertEqual(
            self.kubo.get("healthcheck", {}).get("test"),
            ["CMD-SHELL", "sh /opt/qmesh/kubo-rpc.sh diag healthy >/dev/null 2>&1"],
        )

    def test_rpc_secret_is_available_only_to_trusted_services(self) -> None:
        for name in ("backend", "kubo"):
            self.assertEqual(
                self.model["services"][name]["environment"]["KUBO_RPC_SECRET"],
                "${KUBO_RPC_SECRET:-}",
            )
        self.assertNotIn("KUBO_RPC_SECRET", self.model["services"]["caddy"]["environment"])

    def test_security_hooks_are_read_only_and_cannot_be_silently_missing(self) -> None:
        binds = {m["target"]: m for m in self.kubo["volumes"] if m["type"] == "bind"}
        for target in ("/container-init.d/010-security.sh", "/opt/qmesh/kubo-rpc.sh"):
            self.assertTrue(binds[target]["read_only"])
            self.assertFalse(binds[target]["bind"]["create_host_path"])

    def test_compute_does_not_depend_on_content_health(self) -> None:
        for service in ("backend", "caddy"):
            self.assertNotIn("kubo", self.model["services"][service].get("depends_on", {}))


class SmokeIsolationTests(unittest.TestCase):
    def test_single_and_duplicate_loopback_bindings_are_safe(self) -> None:
        binding = {"HostIp": "127.0.0.1", "HostPort": "18080"}
        for bindings in ([binding], [binding, binding]):
            with self.subTest(bindings=bindings):
                self.assertEqual(smoke_kubo.gateway_port(bindings), "18080")

    def test_missing_public_or_malformed_gateway_bindings_are_rejected(self) -> None:
        safe = {"HostIp": "127.0.0.1", "HostPort": "18080"}
        cases: tuple[object, ...] = (
            None,
            [],
            [{}],
            [{"HostIp": "0.0.0.0", "HostPort": "18080"}],
            [safe, {"HostIp": "::", "HostPort": "18080"}],
            [{"HostIp": "127.0.0.1", "HostPort": "0"}],
            [{"HostIp": "127.0.0.1", "HostPort": "65536"}],
            [{"HostIp": "127.0.0.1", "HostPort": "invalid"}],
        )
        for bindings in cases:
            with self.subTest(bindings=bindings), self.assertRaisesRegex(RuntimeError, "observed"):
                smoke_kubo.gateway_port(bindings)

    def test_failed_start_cleans_only_disposable_resources(self) -> None:
        commands: list[list[str]] = []
        model = {
            "services": {
                "backend": {"environment": {"FIXTURE_SECRET": "must-not-copy"}},
                "kubo": {"ports": [{"target": 8080, "published": "8080"}]},
            },
            "volumes": {"kubo_data": {"name": "existing-data"}},
            "networks": {"content_network": {"name": "existing-network"}},
        }

        def fake_run(command: list[str], data: bytes | None = None) -> bytes:
            commands.append(command)
            if "config" in command:
                self.assertIn("--no-interpolate", command)
                return json.dumps(model).encode()
            if "up" in command:
                path = Path(command[command.index("-f") + 1])
                manifest = json.loads(path.read_text())
                self.assertEqual(list(manifest["services"]), ["kubo"])
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
                self.assertNotIn("must-not-copy", json.dumps(manifest))
                self.assertNotIn("name", manifest["volumes"]["kubo_data"])
                self.assertNotIn("name", manifest["networks"]["content_network"])
                self.assertIn("--offline", manifest["services"]["kubo"]["command"])
                self.assertNotIn("published", manifest["services"]["kubo"]["ports"][0])
                raise subprocess.CalledProcessError(1, command)
            return b""

        with (
            patch.object(sys, "argv", ["smoke_kubo.py"]),
            patch.object(smoke_kubo, "run", side_effect=fake_run),
            contextlib.redirect_stdout(io.StringIO()),
            self.assertRaises(subprocess.CalledProcessError),
        ):
            smoke_kubo.main()
        cleanup = commands[-1]
        self.assertEqual(cleanup[-3:], ["down", "--volumes", "--remove-orphans"])
        self.assertTrue(cleanup[cleanup.index("-p") + 1].startswith("qmesh-kubo-smoke-"))


class SmokeFailureTests(unittest.TestCase):
    def test_rpc_denial_is_not_confused_with_a_broken_daemon_or_success(self) -> None:
        for code, message in ((1, b"connection refused"), (0, b"Kubo RPC Access Denied")):
            result = subprocess.CompletedProcess(["probe"], code, b"", message)
            with (
                self.subTest(code=code),
                patch.object(subprocess, "run", return_value=result),
                self.assertRaisesRegex(RuntimeError, "Expected native RPC authorization denial"),
            ):
                smoke_kubo.require_rpc_denied(["probe"])
        denied = subprocess.CompletedProcess(["probe"], 1, b"", b"Kubo RPC Access Denied")
        with patch.object(subprocess, "run", return_value=denied):
            smoke_kubo.require_rpc_denied(["probe"])

    def test_waits_for_missing_gateway_metadata(self) -> None:
        ready = {"8080/tcp": [{"HostIp": "127.0.0.1", "HostPort": "18080"}]}
        with (
            patch.object(
                smoke_kubo, "run", side_effect=[b'{"8080/tcp": []}', json.dumps(ready).encode()]
            ),
            patch("smoke_kubo.time.sleep") as sleep,
        ):
            self.assertEqual(smoke_kubo.published_gateway("fixture-container"), "18080")
        sleep.assert_called_once_with(0.25)

    def test_unsafe_gateway_binding_is_never_retried(self) -> None:
        unsafe = {"8080/tcp": [{"HostIp": "0.0.0.0", "HostPort": "18080"}]}
        with (
            patch.object(smoke_kubo, "run", return_value=json.dumps(unsafe).encode()),
            patch("smoke_kubo.time.sleep") as sleep,
            self.assertRaisesRegex(RuntimeError, "observed"),
        ):
            smoke_kubo.published_gateway("fixture-container")
        sleep.assert_not_called()

    def test_missing_gateway_metadata_times_out(self) -> None:
        with (
            patch.object(smoke_kubo, "run", return_value=b'{"8080/tcp": []}'),
            patch("smoke_kubo.time.monotonic", side_effect=[0, 11]),
            self.assertRaisesRegex(RuntimeError, r"observed: \[\]"),
        ):
            smoke_kubo.published_gateway("fixture-container")

    def test_published_rpc_is_rejected_before_waiting(self) -> None:
        with (
            patch.object(smoke_kubo, "run", return_value=b'{"5001/tcp": [{}]}'),
            self.assertRaisesRegex(RuntimeError, "RPC port must not"),
        ):
            smoke_kubo.published_gateway("fixture-container")

    def test_command_error_is_actionable_without_leaking_output(self) -> None:
        command = ["docker", "compose", "-p", "fixture", "up", "-d", "kubo"]
        error = subprocess.CalledProcessError(
            7,
            command,
            output=b"fixture-secret",
            stderr=b"fixture-secret",
        )
        with patch.object(subprocess, "run", side_effect=error):
            with self.assertRaisesRegex(
                RuntimeError, r"docker compose up failed \(exit 7\)"
            ) as caught:
                smoke_kubo.run(command)
        self.assertNotIn("fixture-secret", str(caught.exception))
        self.assertTrue(caught.exception.__suppress_context__)

    def test_command_timeout_identifies_the_operation(self) -> None:
        command = ["docker", "compose", "exec", "-T", "kubo", "ipfs", "cat", "fixture"]
        with patch.object(subprocess, "run", side_effect=subprocess.TimeoutExpired(command, 120)):
            with self.assertRaisesRegex(RuntimeError, "docker compose exec timed out after 120"):
                smoke_kubo.run(command)

    def test_cleanup_failure_does_not_replace_primary_error(self) -> None:
        output = io.StringIO()
        with patch.object(smoke_kubo, "run", side_effect=RuntimeError("cleanup failure")):
            with contextlib.redirect_stderr(output), self.assertRaisesRegex(ValueError, "primary"):
                try:
                    raise ValueError("primary")
                finally:
                    smoke_kubo.cleanup(["docker", "compose"], "fixture-project", True)
        self.assertIn("com.docker.compose.project=fixture-project", output.getvalue())

    def test_cleanup_failure_alone_fails_the_smoke(self) -> None:
        with patch.object(smoke_kubo, "run", side_effect=RuntimeError("cleanup failure")):
            with self.assertRaisesRegex(RuntimeError, "cleanup failure"):
                smoke_kubo.cleanup(["docker", "compose"], "fixture-project", False)


if __name__ == "__main__":
    unittest.main()
