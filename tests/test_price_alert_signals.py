"""Price alert structured signal regression tests."""
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PriceAlertSignalTests(unittest.TestCase):
    def _run(self, args, env):
        return subprocess.run(
            [sys.executable, *args],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            timeout=20,
        )

    def test_price_alert_persists_one_signal_per_break(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp, "market.db")
            env = os.environ.copy()
            env["MARKET_DB_URL"] = f"sqlite:///{db_path}"

            migrate = self._run(
                ["-m", "alembic", "-c", "alembic.ini", "upgrade", "head"],
                env,
            )
            self.assertEqual(migrate.returncode, 0, migrate.stderr)

            init = self._run(["-m", "market_monitor.cli", "db", "init"], env)
            self.assertEqual(init.returncode, 0, init.stderr)

            script = textwrap.dedent(
                f"""
                import tempfile
                from unittest import mock

                from market_monitor.monitors.price_alert import PriceAlertMonitor

                class DummyConfig:
                    state_dir = {tmp!r}
                    log_dir = {tmp!r}

                    def get(self, path, default=None):
                        if path == "price_alert.targets":
                            return [
                                {{
                                    "code": "s_sh000001",
                                    "name": "上证指数",
                                    "stop_loss": 3907,
                                    "add_position": 4318,
                                }}
                            ]
                        return default

                def fake_realtime(_codes):
                    return ['var hq_str_s_sh000001="上证指数,3800.00,-107.00,-2.74,0,0";']

                with mock.patch("market_monitor.core.base.get_config", return_value=DummyConfig()), \\
                     mock.patch("market_monitor.core.state.get_config", return_value=DummyConfig()), \\
                     mock.patch("market_monitor.monitors.price_alert.ds.sina_realtime", side_effect=fake_realtime), \\
                     mock.patch("market_monitor.core.base.send_text", return_value=True):
                    ok = PriceAlertMonitor(force=True).run()
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
                    "price_alert",
                    "--json",
                ],
                env,
            )
            self.assertEqual(listed.returncode, 0, listed.stderr)
            payload = json.loads(listed.stdout)
            self.assertEqual(len(payload), 1)
            signal = payload[0]
            self.assertEqual(signal["signal_type"], "price_stop_break")
            self.assertEqual(signal["symbol"], "s_sh000001")
            self.assertEqual(signal["direction"], -1)
            self.assertEqual(signal["level"], 2)
            self.assertIsNotNone(signal["push_log_id"])
            self.assertEqual(signal["metrics"]["trigger"], "stop_break")
            self.assertEqual(signal["metrics"]["threshold"], 3907)


if __name__ == "__main__":
    unittest.main()
