"""Validate managed storage settings without a daemon or private credentials."""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

import smoke_kubo

HOOK = Path(__file__).resolve().parents[1] / "deploy/kubo-storage.sh"


class KuboStorageTests(unittest.TestCase):
    def test_settings_are_validated_before_any_native_configuration(self) -> None:
        cases = [
            (
                {},
                {
                    "Datastore.StorageMax": "10GB",
                    "Datastore.StorageGCWatermark": 90,
                    "Datastore.GCPeriod": "1h",
                },
            ),
            (
                {"KUBO_STORAGE_MAX": "128MB", "KUBO_GC_PERIOD": "30m"},
                {
                    "Datastore.StorageMax": "128MB",
                    "Datastore.StorageGCWatermark": 90,
                    "Datastore.GCPeriod": "30m",
                },
            ),
            (
                {"KUBO_STORAGE_MAX": "2TB", "KUBO_GC_PERIOD": "1s"},
                {
                    "Datastore.StorageMax": "2TB",
                    "Datastore.StorageGCWatermark": 90,
                    "Datastore.GCPeriod": "1s",
                },
            ),
        ]
        for name, invalid in (
            (
                "KUBO_STORAGE_MAX",
                ["0GB", "01GB", "-1GB", "1.5GB", "1GiB", "1000000TB", '1GB"', "1GB\n"],
            ),
            ("KUBO_GC_PERIOD", ["0s", "01h", "-1h", "1.5h", "1d", "1000000h", '1h"', "1h\n"]),
        ):
            cases.extend(({name: value}, None) for value in invalid)
        for overrides, expected in cases:
            with self.subTest(overrides=overrides):
                result, calls = self.invoke(overrides)
                self.assertEqual(result.returncode == 0, expected is not None, result.stderr)
                if expected is None:
                    self.assertEqual(calls, [])
                    self.assertIn("Kubo storage settings", result.stderr)
                else:
                    self.assertEqual({c[2]: json.loads(c[3]) for c in calls}, expected)

    def test_native_failure_is_sanitized(self) -> None:
        result, _ = self.invoke({"CLI_FAIL": "1"})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Kubo storage configuration failed", result.stderr)
        self.assertNotIn("fixture-sensitive-output", result.stdout + result.stderr)

    def test_restart_overwrites_previous_managed_values(self) -> None:
        for maximum in ("10GB", "20GB"):
            result, calls = self.invoke({"KUBO_STORAGE_MAX": maximum})
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(calls[0][3]), maximum)

    def invoke(
        self, overrides: dict[str, str]
    ) -> tuple[subprocess.CompletedProcess[str], list[list[str]]]:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            log = root / "calls.jsonl"
            cli = root / "ipfs"
            cli.write_text(
                f"#!{sys.executable}\n"
                "import json, os, sys\n"
                "with open(os.environ['CLI_LOG'], 'a') as f:\n"
                "    f.write(json.dumps(sys.argv[1:]) + '\\n')\n"
                "if os.environ.get('CLI_FAIL'):\n"
                "    print('fixture-sensitive-output', file=sys.stderr)\n"
                "    sys.exit(1)\n"
            )
            cli.chmod(0o700)
            env = {k: v for k, v in os.environ.items() if not k.startswith("KUBO_")}
            env.update(PATH=f"{root}{os.pathsep}{env['PATH']}", CLI_LOG=str(log), **overrides)
            result = subprocess.run(
                ["sh", str(HOOK)], env=env, capture_output=True, text=True, timeout=10
            )
            return result, [
                json.loads(line) for line in log.read_text().splitlines()
            ] if log.exists() else []


class OperationsSmokeTests(unittest.TestCase):
    def test_gc_requires_a_local_miss_and_retains_the_other_pin(self) -> None:
        for code in (404, 500):
            payload = b""

            def command(args: list[str], data: bytes | None = None) -> bytes:
                nonlocal payload
                if "add" in args:
                    payload = data or b""
                    return b"candidate"
                if args[-1] == "candidate" and "cat" in args:
                    return payload
                return smoke_kubo.FIXTURE

            with (
                self.subTest(code=code),
                patch.object(smoke_kubo, "run", side_effect=command),
                patch.object(smoke_kubo.time, "sleep"),
                patch.object(
                    smoke_kubo.urllib.request,
                    "urlopen",
                    side_effect=urllib.error.HTTPError(
                        "http://fixture/ipfs/candidate", code, "fixture", None, io.BytesIO()
                    ),
                ),
            ):
                if code == 404:
                    smoke_kubo.require_gc_preserves_pins(["cli"], "http://fixture", "retained")
                else:
                    with self.assertRaisesRegex(RuntimeError, "Expected local-only gateway miss"):
                        smoke_kubo.require_gc_preserves_pins(["cli"], "http://fixture", "retained")

    def test_gc_detects_pinned_data_loss_before_unpinning(self) -> None:
        with (
            patch.object(smoke_kubo, "run", side_effect=[b"candidate", b"wrong"]),
            patch.object(smoke_kubo.time, "sleep"),
            self.assertRaisesRegex(RuntimeError, "GC removed pinned DAG content"),
        ):
            smoke_kubo.require_gc_preserves_pins(["cli"], "http://fixture", "retained")

    def test_monitoring_checks_expected_state_and_rejects_published_ui(self) -> None:
        for expected, ports in (("1", {}), ("0", {}), ("1", {"9090/tcp": [{}]})):
            reply = json.dumps(
                {"status": "success", "data": {"result": [{"value": [0, expected]}]}}
            ).encode()
            with (
                self.subTest(expected=expected, ports=ports),
                patch.object(
                    smoke_kubo,
                    "run",
                    side_effect=[reply, b"fixture-container", json.dumps(ports).encode()],
                ),
            ):
                if ports:
                    with self.assertRaisesRegex(RuntimeError, "must not have published ports"):
                        smoke_kubo.require_scrape(["compose"], expected)
                else:
                    smoke_kubo.require_scrape(["compose"], expected)

    def test_monitoring_has_a_bounded_wait_for_successful_scrapes(self) -> None:
        down = json.dumps({"status": "success", "data": {"result": [{"value": [0, "0"]}]}}).encode()
        with (
            patch.object(smoke_kubo, "run", return_value=down),
            patch.object(smoke_kubo.time, "monotonic", side_effect=[0, 61]),
            self.assertRaisesRegex(RuntimeError, "expected Kubo state"),
        ):
            smoke_kubo.require_scrape(["compose"])


if __name__ == "__main__":
    unittest.main()
