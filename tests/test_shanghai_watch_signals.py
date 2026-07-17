"""Shanghai watch structured signal regression tests."""
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ShanghaiWatchSignalTests(unittest.TestCase):
    def _run(self, args, env):
        return subprocess.run(
            [sys.executable, *args],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            timeout=20,
        )

    def test_shanghai_watch_persists_script_signal(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp, "market.db")
            env = os.environ.copy()
            env["MARKET_DB_URL"] = f"sqlite:///{db_path}"

            migrate = self._run(["-m", "alembic", "-c", "alembic.ini", "upgrade", "head"], env)
            self.assertEqual(migrate.returncode, 0, migrate.stderr)

            init = self._run(["-m", "market_monitor.cli", "db", "init"], env)
            self.assertEqual(init.returncode, 0, init.stderr)

            script = textwrap.dedent(
                f"""
                from unittest import mock

                from market_monitor.monitors.shanghai_watch import ShanghaiWatchMonitor

                class DummyConfig:
                    state_dir = {tmp!r}
                    log_dir = {tmp!r}

                    def get(self, path, default=None):
                        if path == "shanghai_watch.enabled":
                            return True
                        return default

                def entry(day, o, h, l, c, v):
                    return {{"day": day, "open": o, "high": h, "low": l, "close": c, "volume": v}}

                kline = []
                for i in range(260):
                    c = 3900.0 + (i - 130) * 0.1
                    kline.append(entry(f"day{{i:03d}}", c - 2, c + 5, c - 5, c, 500 * 1e8))
                kline[-2] = entry("P", 3835, 3840, 3820, 3830, 500 * 1e8)
                kline[-1] = entry("T", 3830, 3835, 3780, 3820, 780 * 1e8)

                with mock.patch("market_monitor.core.base.get_config", return_value=DummyConfig()), \\
                     mock.patch("market_monitor.core.state.get_config", return_value=DummyConfig()), \\
                     mock.patch("market_monitor.monitors.shanghai_watch.ds.get_kline", return_value=kline), \\
                     mock.patch("market_monitor.core.base.send_text", return_value=True):
                    ok = ShanghaiWatchMonitor(force=True).run()
                    print("ok=" + str(ok))
                """
            )
            run = self._run(["-c", script], env)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertIn("ok=True", run.stdout)

            listed = self._run(
                [
                    "-m",
                    "market_monitor.cli",
                    "signal",
                    "list",
                    "--monitor",
                    "shanghai_watch",
                    "--json",
                ],
                env,
            )
            self.assertEqual(listed.returncode, 0, listed.stderr)
            payload = json.loads(listed.stdout)
            types = {row["signal_type"] for row in payload}
            self.assertIn("shanghai_v_reversal", types)

            signal = next(row for row in payload if row["signal_type"] == "shanghai_v_reversal")
            self.assertEqual(signal["symbol"], "sh000001")
            self.assertEqual(signal["direction"], 1)
            self.assertEqual(signal["level"], 3)
            self.assertIsNotNone(signal["push_log_id"])
            self.assertEqual(signal["metrics"]["trigger"], "v_reversal")
            self.assertEqual(signal["metrics"]["close"], 3820.0)


if __name__ == "__main__":
    unittest.main()
