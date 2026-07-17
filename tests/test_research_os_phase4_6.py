"""Research OS phase 4-6 regression tests."""
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ResearchOsPhase46Tests(unittest.TestCase):
    def _env(self, db_path: Path):
        env = os.environ.copy()
        env["MARKET_DB_URL"] = f"sqlite:///{db_path}"
        return env

    def _run(self, args, env, *, timeout=25):
        return subprocess.run(
            [sys.executable, *args],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            timeout=timeout,
        )

    def _init_db(self, env):
        migrate = self._run(["-m", "alembic", "-c", "alembic.ini", "upgrade", "head"], env)
        self.assertEqual(migrate.returncode, 0, migrate.stderr)
        init = self._run(["-m", "market_monitor.cli", "db", "init"], env)
        self.assertEqual(init.returncode, 0, init.stderr)

    def test_signal_action_trade_and_outcome_loop_is_json_readable(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp, "market.db")
            env = self._env(db_path)
            self._init_db(env)

            create_fixture = textwrap.dedent(
                """
                from datetime import datetime, timedelta
                from market_monitor.data import get_session
                from market_monitor.data.models import SymbolOhlcDaily
                from market_monitor.signals import Signal
                from market_monitor.signals.persist import persist_signals

                now = datetime.utcnow().replace(hour=2, minute=0, second=0, microsecond=0)
                with get_session() as s:
                    signal = persist_signals(s, [
                        Signal(
                            monitor="pulse",
                            signal_type="pulse_index_up",
                            symbol="s_sh000001",
                            direction=1,
                            level=2,
                            title="指数拉升测试",
                            metrics={"pct": 1.2},
                            ts=now,
                        )
                    ])[0]
                    for idx, pct in enumerate([0.8, -0.2, 1.5, 0.1, 2.0], start=1):
                        day = (now + timedelta(days=idx)).date()
                        s.merge(SymbolOhlcDaily(
                            symbol="s_sh000001",
                            trade_date=day,
                            open=100,
                            high=102,
                            low=99,
                            close=100 + pct,
                            pct=pct,
                        ))
                    print(signal.id)
                """
            )
            created = self._run(["-c", create_fixture], env)
            self.assertEqual(created.returncode, 0, created.stderr)
            signal_id = int(created.stdout.strip())

            marked = self._run(
                [
                    "-m", "market_monitor.cli", "signal", "mark", str(signal_id),
                    "--decision", "skip", "--reason", "等待确认", "--json",
                ],
                env,
            )
            self.assertEqual(marked.returncode, 0, marked.stderr)
            mark_payload = json.loads(marked.stdout)
            self.assertTrue(mark_payload["ok"])
            self.assertEqual(mark_payload["decision"], "skip")

            added = self._run(
                [
                    "-m", "market_monitor.cli", "trade", "add",
                    "s_sh000001", "100", "10",
                    "--signal-id", str(signal_id),
                    "--reason", "跟随信号试单",
                    "--json",
                ],
                env,
            )
            self.assertEqual(added.returncode, 0, added.stderr)
            trade_payload = json.loads(added.stdout)
            self.assertEqual(trade_payload["signal_event_id"], signal_id)
            self.assertIsNotNone(trade_payload["signal_link_id"])

            listed = self._run(
                ["-m", "market_monitor.cli", "trade", "list", "--all", "--json"],
                env,
            )
            self.assertEqual(listed.returncode, 0, listed.stderr)
            trade_list = json.loads(listed.stdout)
            self.assertEqual(trade_list["open"][0]["signal_event_id"], signal_id)

            backfilled = self._run(
                [
                    "-m", "market_monitor.cli", "signal", "outcome", "backfill",
                    "--days", "7", "--json",
                ],
                env,
            )
            self.assertEqual(backfilled.returncode, 0, backfilled.stderr)
            outcome_payload = json.loads(backfilled.stdout)
            self.assertEqual(outcome_payload["count"], 1)
            outcome = outcome_payload["outcomes"][0]
            self.assertEqual(outcome["signal_event_id"], signal_id)
            self.assertEqual(outcome["predicted_direction"], 1)
            self.assertEqual(outcome["t1_pct"], 0.8)
            self.assertEqual(outcome["t3_pct"], 1.5)
            self.assertEqual(outcome["t5_pct"], 2.0)
            self.assertTrue(outcome["t1_hit"])

    def test_decision_import_sql_and_research_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp, "market.db")
            env = self._env(db_path)
            self._init_db(env)

            decision_path = Path(tmp, "2026-07-17.jsonl")
            decision_path.write_text(
                json.dumps(
                    {
                        "id": "2026-07-17-000",
                        "date": "2026-07-17",
                        "claim": "上证短期企稳",
                        "direction": "bullish",
                        "subject": "上证指数",
                        "timeframe": "short-term",
                        "source_type": "morning",
                        "confidence": "explicit",
                        "extracted_at": "2026-07-17T09:00:00",
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )

            imported = self._run(
                [
                    "-m", "market_monitor.cli", "decision", "import-sql",
                    "--date", "2026-07-17",
                    "--path", str(decision_path),
                    "--json",
                ],
                env,
            )
            self.assertEqual(imported.returncode, 0, imported.stderr)
            import_payload = json.loads(imported.stdout)
            self.assertEqual(import_payload["read"], 1)
            self.assertEqual(import_payload["created"], 1)

            signals = self._run(
                [
                    "-m", "market_monitor.cli", "signal", "list",
                    "--monitor", "decision", "--days", "365", "--json",
                ],
                env,
            )
            self.assertEqual(signals.returncode, 0, signals.stderr)
            signal_payload = json.loads(signals.stdout)
            self.assertEqual(signal_payload[0]["signal_type"], "decision_bullish")
            self.assertEqual(signal_payload[0]["metrics"]["decision_id"], "2026-07-17-000")

            out_path = Path(tmp, "research.html")
            exported = self._run(
                [
                    "-m", "market_monitor.cli", "research", "export",
                    "--out", str(out_path),
                    "--days", "365",
                    "--json",
                ],
                env,
            )
            self.assertEqual(exported.returncode, 0, exported.stderr)
            export_payload = json.loads(exported.stdout)
            self.assertTrue(out_path.exists())
            self.assertEqual(export_payload["signals"], 1)
            html = out_path.read_text(encoding="utf-8")
            self.assertIn("Market Research OS", html)
            self.assertIn("上证短期企稳", html)


if __name__ == "__main__":
    unittest.main()
