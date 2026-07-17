"""Structured signal CLI regression tests."""
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class SignalCliTests(unittest.TestCase):
    def _env(self, db_path: Path):
        env = os.environ.copy()
        env["MARKET_DB_URL"] = f"sqlite:///{db_path}"
        return env

    def _run(self, args, env, *, input_text=None):
        return subprocess.run(
            [sys.executable, *args],
            cwd=ROOT,
            env=env,
            input=input_text,
            text=True,
            capture_output=True,
            timeout=20,
        )

    def test_signal_json_commands_are_machine_readable(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp, "market.db")
            env = self._env(db_path)

            migrate = self._run(
                ["-m", "alembic", "-c", "alembic.ini", "upgrade", "head"],
                env,
            )
            self.assertEqual(migrate.returncode, 0, migrate.stderr)

            init = self._run(["-m", "market_monitor.cli", "db", "init"], env)
            self.assertEqual(init.returncode, 0, init.stderr)

            create_signal = textwrap.dedent(
                """
                from market_monitor.data import get_session
                from market_monitor.signals import Signal
                from market_monitor.signals.persist import persist_signals

                with get_session() as s:
                    rows = persist_signals(s, [
                        Signal(
                            monitor="pulse",
                            signal_type="pulse_index_down",
                            symbol="s_sh000001",
                            symbols=["s_sh000001", "s_sz399006"],
                            level=2,
                            title="指数回落测试",
                            metrics={"pct": -1.6},
                        )
                    ])
                    print(rows[0].id)
                """
            )
            created = self._run(["-c", create_signal], env)
            self.assertEqual(created.returncode, 0, created.stderr)
            signal_id = int(created.stdout.strip())

            types = self._run(
                ["-m", "market_monitor.cli", "signal", "types", "--monitor", "pulse", "--json"],
                env,
            )
            self.assertEqual(types.returncode, 0, types.stderr)
            type_payload = json.loads(types.stdout)
            self.assertTrue(any(r["signal_type"] == "pulse_index_down" for r in type_payload))

            listed = self._run(
                ["-m", "market_monitor.cli", "signal", "list", "--days", "7", "--json"],
                env,
            )
            self.assertEqual(listed.returncode, 0, listed.stderr)
            list_payload = json.loads(listed.stdout)
            self.assertEqual(len(list_payload), 1)
            self.assertEqual(list_payload[0]["id"], signal_id)
            self.assertEqual(list_payload[0]["signal_type"], "pulse_index_down")
            self.assertEqual(list_payload[0]["symbols"], ["s_sh000001", "s_sz399006"])
            self.assertEqual(list_payload[0]["metrics"]["pct"], -1.6)

            shown = self._run(
                ["-m", "market_monitor.cli", "signal", "show", str(signal_id), "--json"],
                env,
            )
            self.assertEqual(shown.returncode, 0, shown.stderr)
            show_payload = json.loads(shown.stdout)
            self.assertEqual(show_payload["id"], signal_id)
            self.assertEqual(show_payload["title"], "指数回落测试")


if __name__ == "__main__":
    unittest.main()
