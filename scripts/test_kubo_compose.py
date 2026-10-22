"""Check the content-node deployment contract without starting any services."""

from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path
from typing import Any, ClassVar

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
        self.assertIn("backend_network", self.kubo.get("networks", {}))
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
            [
                "CMD",
                "ipfs",
                "--api=/ip4/127.0.0.1/tcp/5001",
                "diag",
                "healthy",
            ],
        )

    def test_compute_does_not_depend_on_content_health(self) -> None:
        for service in ("backend", "caddy"):
            self.assertNotIn("kubo", self.model["services"][service].get("depends_on", {}))


if __name__ == "__main__":
    unittest.main()
