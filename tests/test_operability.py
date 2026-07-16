"""Operability regression tests for CLI and installation behavior."""
import argparse
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]


class CliOperabilityTests(unittest.TestCase):
    def test_cli_list_does_not_require_monitor_runtime_dependencies_or_config(self):
        result = subprocess.run(
            [sys.executable, "-m", "market_monitor.cli", "list"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=10,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("stabilize", result.stdout)
        self.assertIn("morning", result.stdout)
        self.assertEqual(result.stderr, "")

    def test_doctor_ci_checks_portable_project_invariants(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = os.environ.copy()
            env["MARKET_MONITOR_LAUNCHD_DIR"] = tmp

            gen = subprocess.run(
                [sys.executable, "scripts/gen_launchd.py"],
                cwd=ROOT,
                text=True,
                capture_output=True,
                timeout=10,
                env=env,
            )
            self.assertEqual(gen.returncode, 0, gen.stderr)

            result = subprocess.run(
                [sys.executable, "-m", "market_monitor.cli", "doctor", "--ci"],
                cwd=ROOT,
                text=True,
                capture_output=True,
                timeout=10,
                env=env,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("python", result.stdout.lower())
            self.assertIn("launchd", result.stdout.lower())
            self.assertIn("registry", result.stdout.lower())

    def test_doctor_reports_missing_local_config(self):
        config_path = ROOT / "config" / "config.yaml"
        if config_path.exists():
            self.skipTest("local config exists on this machine")

        result = subprocess.run(
            [sys.executable, "-m", "market_monitor.cli", "doctor"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=10,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("config/config.yaml", result.stdout)

    def test_decision_review_defaults_to_last_seven_days(self):
        from market_monitor import cli

        args = argparse.Namespace(
            week=False,
            start=None,
            end=None,
            push=False,
        )

        with mock.patch.object(cli, "send_text", create=True), mock.patch(
            "market_monitor.core.decision_tracker.format_weekly_review",
            return_value="weekly report",
        ) as format_weekly:
            with mock.patch("builtins.print") as mocked_print:
                cli.cmd_decision_review(args)

        self.assertTrue(format_weekly.called)
        mocked_print.assert_any_call("weekly report")


class LaunchdGenerationTests(unittest.TestCase):
    def test_gen_launchd_uses_python_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = os.environ.copy()
            env["MARKET_MONITOR_LAUNCHD_DIR"] = tmp
            env["MARKET_MONITOR_PYTHON"] = "/custom/python"

            result = subprocess.run(
                [sys.executable, "scripts/gen_launchd.py"],
                cwd=ROOT,
                text=True,
                capture_output=True,
                timeout=10,
                env=env,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            plist = Path(tmp, "com.market-monitor.stabilize.plist").read_text(
                encoding="utf-8"
            )
            self.assertIn("<string>/custom/python</string>", plist)
            self.assertIn(f"<string>{ROOT}</string>", plist)

    def test_gen_launchd_covers_monthly_day_schedule(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = os.environ.copy()
            env["MARKET_MONITOR_LAUNCHD_DIR"] = tmp

            result = subprocess.run(
                [sys.executable, "scripts/gen_launchd.py"],
                cwd=ROOT,
                text=True,
                capture_output=True,
                timeout=10,
                env=env,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            plist = Path(tmp, "com.market-monitor.monthly.plist").read_text(
                encoding="utf-8"
            )
            self.assertIn("<key>Day</key>", plist)
            self.assertIn("<integer>1</integer>", plist)


class CliConfigTests(unittest.TestCase):
    def test_cmd_run_skips_disabled_monitor_unless_forced(self):
        from market_monitor import cli

        class DummyMonitor:
            name = "dummy"
            display_name = "Dummy"

            def __init__(self, *args, **kwargs):
                raise AssertionError("disabled monitor should not be instantiated")

        class DummyConfig:
            def get(self, path, default=None):
                if path == "dummy.enabled":
                    return False
                return default

        args = argparse.Namespace(name="dummy", force=False, snapshot=False)

        with mock.patch.object(cli, "get_monitor", return_value=DummyMonitor), mock.patch(
            "market_monitor.cli.get_config", return_value=DummyConfig(), create=True
        ):
            with self.assertRaises(SystemExit) as cm:
                cli.cmd_run(args)

        self.assertEqual(cm.exception.code, 0)

    def test_cmd_run_executes_disabled_monitor_when_forced(self):
        from market_monitor import cli

        calls = []

        class DummyMonitor:
            name = "dummy"
            display_name = "Dummy"

            def __init__(self, force=False, snapshot=False):
                calls.append(("init", force, snapshot))

            def run(self):
                calls.append(("run",))
                return True

        class DummyConfig:
            def get(self, path, default=None):
                if path == "dummy.enabled":
                    return False
                return default

        args = argparse.Namespace(name="dummy", force=True, snapshot=False)

        with mock.patch.object(cli, "get_monitor", return_value=DummyMonitor), mock.patch(
            "market_monitor.cli.get_config", return_value=DummyConfig(), create=True
        ):
            with self.assertRaises(SystemExit) as cm:
                cli.cmd_run(args)

        self.assertEqual(cm.exception.code, 0)
        self.assertEqual(calls, [("init", True, False), ("run",)])


if __name__ == "__main__":
    unittest.main()
