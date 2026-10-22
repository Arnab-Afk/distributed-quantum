"""Exercise init hooks with a fake CLI; no daemon, credentials or providers needed."""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TOKEN = "fixture-token-with-at-least-32-characters"
INIT = ROOT / "deploy/kubo-init.sh"
RPC = ROOT / "deploy/kubo-rpc.sh"


class KuboSecurityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name)
        self.log = self.path / "calls.jsonl"
        (self.path / "config").write_text("{}")
        fake = self.path / "ipfs"
        fake.write_text(
            f"#!{sys.executable}\n"
            "import json, os, sys\n"
            "with open(os.environ['CLI_LOG'], 'a') as f:\n"
            "    f.write(json.dumps(sys.argv[1:]) + '\\n')\n"
            "if os.environ.get('CLI_FAIL'):\n"
            "    print(os.environ.get('KUBO_RPC_SECRET', ''), file=sys.stderr)\n"
            "    sys.exit(1)\n"
        )
        fake.chmod(0o700)
        self.env = {
            **os.environ,
            "PATH": f"{self.path}{os.pathsep}{os.environ['PATH']}",
            "IPFS_PATH": str(self.path),
            "CLI_LOG": str(self.log),
            "KUBO_RPC_SECRET": TOKEN,
        }

    def invoke(self, script: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["sh", str(script), *args],
            env=self.env,
            capture_output=True,
            text=True,
            timeout=10,
        )

    def settings(self) -> dict[str, Any]:
        calls = [json.loads(line) for line in self.log.read_text().splitlines()]
        return {call[2]: json.loads(call[3]) for call in calls}

    def test_init_limits_backend_paths_and_gateway(self) -> None:
        result = self.invoke(INIT)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn(TOKEN, result.stdout + result.stderr)
        config = self.settings()
        auth = config["API.Authorizations"]
        self.assertIsInstance(auth, dict)
        scope = auth["backend"]
        self.assertEqual(scope["AuthSecret"], f"bearer:{TOKEN}")
        self.assertEqual(
            set(scope["AllowedPaths"]),
            {
                "/api/v0/id",
                "/api/v0/diag/healthy",
                "/api/v0/add",
                "/api/v0/cat",
                "/api/v0/pin/add",
                "/api/v0/pin/rm",
                "/api/v0/pin/ls",
                "/api/v0/dag/import",
                "/api/v0/block/stat",
            },
        )
        self.assertIs(config["Gateway.NoFetch"], True)
        self.assertIs(config["Gateway.NoDNSLink"], True)
        self.assertIs(config["Gateway.ExposeRoutingAPI"], False)
        self.assertNotIn("Gateway.Writable", config)
        self.assertEqual(config["Swarm.ConnMgr.LowWater"], 32)
        self.assertEqual(config["Swarm.ConnMgr.HighWater"], 96)
        self.assertIs(config["Swarm.ResourceMgr.Enabled"], True)
        self.assertEqual(config["Swarm.ResourceMgr.MaxFileDescriptors"], 1024)
        self.assertIs(config["Swarm.RelayService.Enabled"], False)
        self.assertEqual(config["AutoNAT.ServiceMode"], "disabled")
        self.assertEqual(stat.S_IMODE((self.path / "config").stat().st_mode), 0o600)

    def test_missing_or_unsafe_secret_fails_closed_without_leaking(self) -> None:
        for script in (INIT, RPC):
            for secret in ("", "short", "x" * 32 + "'", "x" * 32 + "\n", "x" * 32 + "é", "x" * 129):
                self.env["KUBO_RPC_SECRET"] = secret
                with self.subTest(script=script.name, length=len(secret)):
                    result = self.invoke(script)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("secret", result.stderr)
                    self.assertFalse(self.log.exists())
                    if secret:
                        self.assertNotIn(secret, result.stdout + result.stderr)

    def test_native_config_error_does_not_leak_secret(self) -> None:
        self.env["CLI_FAIL"] = "1"
        result = self.invoke(INIT)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("security configuration failed", result.stderr)
        self.assertTrue(self.log.exists())
        self.assertNotIn(TOKEN, result.stdout + result.stderr)

    def test_restart_reapplies_rotated_secret(self) -> None:
        self.assertEqual(self.invoke(INIT).returncode, 0)
        self.env["KUBO_RPC_SECRET"] = "rotated-fixture-token-with-32-characters"
        self.assertEqual(self.invoke(INIT).returncode, 0)
        self.assertEqual(
            self.settings()["API.Authorizations"]["backend"]["AuthSecret"],
            f"bearer:{self.env['KUBO_RPC_SECRET']}",
        )

    def test_rpc_wrapper_reads_secret_in_container_not_host_argv(self) -> None:
        result = self.invoke(RPC, "id")
        self.assertEqual(result.returncode, 0, result.stderr)
        call = json.loads(self.log.read_text().splitlines()[0])
        self.assertIn(f"--api-auth=bearer:{TOKEN}", call)
        self.assertEqual(call[-1], "id")
        self.assertNotIn(TOKEN, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
