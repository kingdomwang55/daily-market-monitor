"""Report configuration behavior tests."""
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ReportAiConfigTests(unittest.TestCase):
    def test_importing_report_monitor_does_not_emit_optional_db_warning(self):
        result = subprocess.run(
            [sys.executable, "-c", "import market_monitor.monitors.morning"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=10,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")

    def test_morning_ai_requires_report_and_global_ai_switches(self):
        from market_monitor.monitors.morning import MorningMonitor

        class DummyConfig:
            def __init__(self, values):
                self.values = values

            def get(self, path, default=None):
                return self.values.get(path, default)

        monitor = MorningMonitor.__new__(MorningMonitor)
        monitor.config = DummyConfig({
            "morning_report.use_ai": False,
            "ai.enabled": True,
        })
        self.assertFalse(monitor._ai_enabled())

        monitor.config = DummyConfig({
            "morning_report.use_ai": True,
            "ai.enabled": False,
        })
        self.assertFalse(monitor._ai_enabled())

        monitor.config = DummyConfig({
            "morning_report.use_ai": True,
            "ai.enabled": True,
        })
        self.assertTrue(monitor._ai_enabled())

    def test_evening_ai_requires_report_and_global_ai_switches(self):
        from market_monitor.monitors.evening import EveningMonitor

        class DummyConfig:
            def __init__(self, values):
                self.values = values

            def get(self, path, default=None):
                return self.values.get(path, default)

        monitor = EveningMonitor.__new__(EveningMonitor)
        monitor.config = DummyConfig({
            "evening_report.use_ai": False,
            "ai.enabled": True,
        })
        self.assertFalse(monitor._ai_enabled())

        monitor.config = DummyConfig({
            "evening_report.use_ai": True,
            "ai.enabled": False,
        })
        self.assertFalse(monitor._ai_enabled())

        monitor.config = DummyConfig({
            "evening_report.use_ai": True,
            "ai.enabled": True,
        })
        self.assertTrue(monitor._ai_enabled())


if __name__ == "__main__":
    unittest.main()
