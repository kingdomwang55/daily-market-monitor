"""HK shock structured signal regression tests."""
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class HkShockSignalTests(unittest.TestCase):
    def _run(self, args, env):
        return subprocess.run(
            [sys.executable, *args],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            timeout=20,
        )

    def test_hk_shock_persists_cross_market_scenario_signals(self):
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
                from datetime import datetime
                from unittest import mock

                from market_monitor.monitors.hk_shock import HkShockMonitor

                class DummyConfig:
                    state_dir = {tmp!r}
                    log_dir = {tmp!r}

                    def get(self, path, default=None):
                        if path == "hk_shock.indices":
                            return [
                                {{"code": "hkHSI", "name": "恒生指数", "type": "broad"}},
                            ]
                        if path == "hk_shock.stocks":
                            return []
                        if path == "hk_shock.a_share_ref":
                            return [
                                {{"code": "s_sh000001", "name": "上证指数"}},
                            ]
                        if path == "hk_shock.thresholds_index":
                            return [1.5, 2.5, 3.5]
                        if path == "hk_shock.thresholds_tech":
                            return [2.0, 3.5, 5.0]
                        if path == "hk_shock.thresholds_stock":
                            return [3.0, 5.0, 7.0]
                        if path == "hk_shock.a_share_diverge_threshold":
                            return 1.0
                        return default

                def fake_realtime(codes):
                    if codes == ["hkHSI"]:
                        return [
                            'var hq_str_hkHSI="HSI,恒生指数,23000.00,23000.00,23100.00,22400.00,22500.00,-500.00,-2.17,0,0,0,0,28056.10,22518.00,2026/07/17,10:00";'
                        ]
                    if codes == ["s_sh000001"]:
                        return [
                            'var hq_str_s_sh000001="上证指数,3800.00,-50.00,-1.30,0,0";'
                        ]
                    return []

                with mock.patch("market_monitor.core.base.get_config", return_value=DummyConfig()), \\
                     mock.patch("market_monitor.core.state.get_config", return_value=DummyConfig()), \\
                     mock.patch("market_monitor.monitors.hk_shock.ds.sina_realtime", side_effect=fake_realtime), \\
                     mock.patch("market_monitor.core.base.send_text", return_value=True):
                    monitor = HkShockMonitor(force=True)
                    monitor.now = datetime(2026, 7, 17, 10, 0)
                    ok = monitor.run()
                    print("ok=" + str(ok))
                """
            )
            run = self._run(["-c", script], env)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertIn("ok=True", run.stdout)

            listed = self._run(
                ["-m", "market_monitor.cli", "signal", "list", "--monitor", "hk_shock", "--json"],
                env,
            )
            self.assertEqual(listed.returncode, 0, listed.stderr)
            payload = json.loads(listed.stdout)
            self.assertEqual(len(payload), 1)

            signal = payload[0]
            self.assertEqual(signal["signal_type"], "hk_resonance_down")
            self.assertEqual(signal["symbol"], "hkHSI")
            self.assertEqual(signal["direction"], -1)
            self.assertEqual(signal["level"], 1)
            self.assertIsNotNone(signal["push_log_id"])
            self.assertEqual(signal["metrics"]["trigger"], "hk_index_move")
            self.assertEqual(signal["metrics"]["scenario"], "resonance_down")
            self.assertEqual(signal["metrics"]["a_stage"], "live")
            self.assertAlmostEqual(signal["metrics"]["hk_avg_pct"], -2.17)
            self.assertAlmostEqual(signal["metrics"]["a_avg_pct"], -1.3)


if __name__ == "__main__":
    unittest.main()
