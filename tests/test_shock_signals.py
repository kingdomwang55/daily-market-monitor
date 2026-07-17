"""Shock monitor structured signal regression tests."""
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ShockSignalTests(unittest.TestCase):
    def _run(self, args, env):
        return subprocess.run(
            [sys.executable, *args],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            timeout=20,
        )

    def test_shock_persists_index_and_sector_signals(self):
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
                from unittest import mock

                from market_monitor.monitors.shock import ShockMonitor

                class DummyConfig:
                    state_dir = {tmp!r}
                    log_dir = {tmp!r}

                    def get(self, path, default=None):
                        if path == "shock.indices":
                            return [
                                {{"code": "s_sh000001", "name": "上证指数"}},
                                {{"code": "s_sz399006", "name": "创业板指"}},
                            ]
                        if path == "shock.thresholds":
                            return [1.5, 2.5, 3.5]
                        if path == "shock.sector_threshold":
                            return 4.0
                        return default

                def fake_realtime(_codes):
                    return [
                        'var hq_str_s_sh000001="上证指数,3800.00,-107.00,-2.74,0,0";',
                        'var hq_str_s_sz399006="创业板指,2200.00,-10.00,-0.45,0,0";',
                    ]

                def fake_sectors():
                    return [
                        {{"name": "半导体", "pct": -4.6}},
                        {{"name": "银行", "pct": 0.5}},
                    ]

                with mock.patch("market_monitor.core.base.get_config", return_value=DummyConfig()), \\
                     mock.patch("market_monitor.core.state.get_config", return_value=DummyConfig()), \\
                     mock.patch("market_monitor.monitors.shock.ds.sina_realtime", side_effect=fake_realtime), \\
                     mock.patch("market_monitor.monitors.shock.ds.eastmoney_sectors", side_effect=fake_sectors), \\
                     mock.patch("market_monitor.core.base.send_text", return_value=True):
                    ok = ShockMonitor(force=True).run()
                    print("ok=" + str(ok))
                """
            )
            run = self._run(["-c", script], env)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertIn("ok=True", run.stdout)

            listed = self._run(
                ["-m", "market_monitor.cli", "signal", "list", "--monitor", "shock", "--json"],
                env,
            )
            self.assertEqual(listed.returncode, 0, listed.stderr)
            payload = json.loads(listed.stdout)
            self.assertEqual(len(payload), 2)

            by_type = {row["signal_type"]: row for row in payload}
            self.assertIn("shock_index_down_L2", by_type)
            self.assertIn("shock_sector_only", by_type)

            index_signal = by_type["shock_index_down_L2"]
            self.assertEqual(index_signal["symbol"], "s_sh000001")
            self.assertEqual(index_signal["direction"], -1)
            self.assertEqual(index_signal["level"], 2)
            self.assertEqual(index_signal["metrics"]["trigger"], "index_move")
            self.assertIsNotNone(index_signal["push_log_id"])

            sector_signal = by_type["shock_sector_only"]
            self.assertEqual(sector_signal["direction"], -1)
            self.assertEqual(sector_signal["level"], 2)
            self.assertEqual(sector_signal["metrics"]["name"], "半导体")
            self.assertEqual(sector_signal["metrics"]["trigger"], "sector_move")
            self.assertEqual(sector_signal["push_log_id"], index_signal["push_log_id"])


if __name__ == "__main__":
    unittest.main()
