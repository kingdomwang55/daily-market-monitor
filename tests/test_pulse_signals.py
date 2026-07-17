"""Pulse monitor structured signal regression tests."""
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PulseSignalTests(unittest.TestCase):
    def _run(self, args, env):
        return subprocess.run(
            [sys.executable, *args],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            timeout=20,
        )

    def test_pulse_persists_multiple_trigger_families(self):
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

                from market_monitor.monitors.pulse import PulseMonitor

                class DummyConfig:
                    state_dir = {tmp!r}
                    log_dir = {tmp!r}

                    def get(self, path, default=None):
                        if path == "stabilize.symbols":
                            return [{{"code": "s_sh000001", "name": "上证指数"}}]
                        if path == "price_alert.targets":
                            return [
                                {{
                                    "code": "s_sh000001",
                                    "name": "上证指数",
                                    "stop_loss": 3900,
                                    "add_position": 4318,
                                }}
                            ]
                        if path == "defensive_assets":
                            return [
                                {{"code": "sh518880", "name": "黄金ETF", "category": "黄金/避险"}}
                            ]
                        return default

                def fake_index_snapshot(self):
                    return [
                        {{"name": "上证指数", "code": "s_sh000001", "price": 3925.0, "pct": -1.6}}
                    ]

                with mock.patch("market_monitor.core.base.get_config", return_value=DummyConfig()), \\
                     mock.patch("market_monitor.core.state.get_config", return_value=DummyConfig()), \\
                     mock.patch.object(PulseMonitor, "_index_snapshot", fake_index_snapshot), \\
                     mock.patch.object(PulseMonitor, "_key_level_proximity", return_value=["⚠️ 上证指数 逼近止损"]), \\
                     mock.patch.object(PulseMonitor, "_stabilize_signals", return_value=None), \\
                     mock.patch.object(PulseMonitor, "_sector_shock", return_value=[{{"name": "半导体", "pct": -2.4}}]), \\
                     mock.patch.object(PulseMonitor, "_defensive_shock", return_value=[{{"name": "黄金ETF", "category": "黄金/避险", "price": 6.0, "pct": 1.2}}]), \\
                     mock.patch("market_monitor.core.base.send_text", return_value=True):
                    ok = PulseMonitor(force=True).run()
                    print("ok=" + str(ok))
                """
            )
            run = self._run(["-c", script], env)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertIn("ok=True", run.stdout)

            listed = self._run(
                ["-m", "market_monitor.cli", "signal", "list", "--monitor", "pulse", "--json"],
                env,
            )
            self.assertEqual(listed.returncode, 0, listed.stderr)
            payload = json.loads(listed.stdout)
            signal_types = {row["signal_type"] for row in payload}

            self.assertIn("pulse_index_down", signal_types)
            self.assertIn("pulse_near_key_level", signal_types)
            self.assertIn("pulse_sector_move", signal_types)
            self.assertIn("pulse_defensive", signal_types)

            push_ids = {row["push_log_id"] for row in payload}
            self.assertEqual(len(push_ids), 1)
            self.assertNotIn(None, push_ids)

            index_signal = next(row for row in payload if row["signal_type"] == "pulse_index_down")
            self.assertEqual(index_signal["symbol"], "s_sh000001")
            self.assertEqual(index_signal["direction"], -1)
            self.assertEqual(index_signal["metrics"]["trigger"], "index_move")


if __name__ == "__main__":
    unittest.main()
