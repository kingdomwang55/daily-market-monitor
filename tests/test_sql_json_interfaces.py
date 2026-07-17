"""SQL read-side JSON interface regression tests."""
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class SqlJsonInterfaceTests(unittest.TestCase):
    def _run(self, args, env):
        return subprocess.run(
            [sys.executable, *args],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            timeout=20,
        )

    def test_db_json_includes_linked_signals_and_signal_push_filter(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp, "market.db")
            env = os.environ.copy()
            env["MARKET_DB_URL"] = f"sqlite:///{db_path}"

            migrate = self._run(["-m", "alembic", "-c", "alembic.ini", "upgrade", "head"], env)
            self.assertEqual(migrate.returncode, 0, migrate.stderr)

            init = self._run(["-m", "market_monitor.cli", "db", "init"], env)
            self.assertEqual(init.returncode, 0, init.stderr)

            setup = textwrap.dedent(
                """
                from market_monitor.data import get_session
                from market_monitor.data.repositories import PushLogRepository
                from market_monitor.signals import Signal
                from market_monitor.signals.persist import persist_signals

                with get_session() as s:
                    push = PushLogRepository(s).create(
                        monitor="pulse",
                        message="pulse test message",
                        scenario="pulse_index_down",
                        max_level=2,
                        title="Pulse Test",
                        sent_ok=True,
                    )
                    rows = persist_signals(s, [
                        Signal(
                            monitor="pulse",
                            signal_type="pulse_index_down",
                            title="指数回落",
                            symbol="s_sh000001",
                            direction=-1,
                            level=2,
                            metrics={"pct": -1.6},
                            push_log_id=push.id,
                        )
                    ])
                    print(f"{push.id},{rows[0].id}")
                """
            )
            created = self._run(["-c", setup], env)
            self.assertEqual(created.returncode, 0, created.stderr)
            push_id, signal_id = [int(x) for x in created.stdout.strip().split(",")]

            db_query = self._run(
                ["-m", "market_monitor.cli", "db", "query", "--days", "7", "--json"],
                env,
            )
            self.assertEqual(db_query.returncode, 0, db_query.stderr)
            pushes = json.loads(db_query.stdout)
            self.assertEqual(len(pushes), 1)
            self.assertEqual(pushes[0]["id"], push_id)
            self.assertEqual(pushes[0]["signal_ids"], [signal_id])
            self.assertEqual(pushes[0]["signal_types"], ["pulse_index_down"])

            signal_list = self._run(
                [
                    "-m",
                    "market_monitor.cli",
                    "signal",
                    "list",
                    "--push-id",
                    str(push_id),
                    "--json",
                ],
                env,
            )
            self.assertEqual(signal_list.returncode, 0, signal_list.stderr)
            signals = json.loads(signal_list.stdout)
            self.assertEqual(len(signals), 1)
            self.assertEqual(signals[0]["id"], signal_id)
            self.assertEqual(signals[0]["push_log_id"], push_id)

            db_stats = self._run(
                ["-m", "market_monitor.cli", "db", "stats", "--days", "7", "--json"],
                env,
            )
            self.assertEqual(db_stats.returncode, 0, db_stats.stderr)
            stats = json.loads(db_stats.stdout)
            self.assertEqual(stats["days"], 7)
            self.assertEqual(stats["monitor_stats"][0]["monitor"], "pulse")
            self.assertEqual(stats["signal_frequency"][0]["signal_type"], "pulse_index_down")

            db_info = self._run(["-m", "market_monitor.cli", "db", "info", "--json"], env)
            self.assertEqual(db_info.returncode, 0, db_info.stderr)
            info = json.loads(db_info.stdout)
            self.assertIn("database", info)
            self.assertTrue(any(row["table"] == "signal_event" for row in info["tables"]))


if __name__ == "__main__":
    unittest.main()
