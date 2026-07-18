"""FastAPI and Vue serving regression tests."""

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from market_monitor.api.deps import get_db_session
from market_monitor.api.server import create_app
from market_monitor.data.models import (
    Base,
    MonitorRegistry,
    PaperTrade,
    PushLog,
    SignalEvent,
    SignalOutcome,
    SignalTypeRegistry,
    TradeSignalLink,
)


class WebApiTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.session = sessionmaker(bind=self.engine, expire_on_commit=False)()
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        self.session.add_all([
            MonitorRegistry(name="pulse", display_name="盘中脉搏", category="periodic"),
            MonitorRegistry(name="hk_shock", display_name="港股异动", category="shock"),
            SignalTypeRegistry(
                signal_type="pulse_index_down",
                monitor="pulse",
                display_name="盘中指数回落",
                direction=-1,
            ),
            SignalTypeRegistry(
                signal_type="hk_index_down",
                monitor="hk_shock",
                display_name="港股急跌",
                direction=-1,
            ),
        ])
        self.session.flush()
        push = PushLog(
            ts=now,
            trade_date=date.today(),
            monitor="pulse",
            max_level=2,
            title="盘中风险提示",
            message="指数回落，注意仓位。",
            context_json={"source": "test"},
            sent_ok=True,
        )
        self.session.add(push)
        self.session.flush()
        pulse_signal = SignalEvent(
                ts=now,
                trade_date=date.today(),
                monitor="pulse",
                signal_type="pulse_index_down",
                symbol="s_sh000001",
                level=2,
                metrics_json={"title": "指数回落", "pct": -1.6},
                push_log_id=push.id,
            )
        hk_signal = SignalEvent(
                ts=now - timedelta(hours=1),
                trade_date=date.today(),
                monitor="hk_shock",
                signal_type="hk_index_down",
                symbol="hkHSI",
                level=3,
                metrics_json={"title": "港股急跌", "pct": -3.1},
            )
        self.session.add_all([pulse_signal, hk_signal])
        self.session.flush()
        trade = PaperTrade(
            symbol="s_sh000001",
            name="上证指数测试",
            entry_at=now,
            entry_price=3500.0,
            qty=1,
            status="open",
            signal_event_id=pulse_signal.id,
        )
        self.session.add(trade)
        self.session.flush()
        self.session.add_all([
            TradeSignalLink(
                signal_event_id=pulse_signal.id,
                paper_trade_id=trade.id,
                decision="act",
                reason="测试关联",
            ),
            SignalOutcome(
                signal_event_id=hk_signal.id,
                signal_type=hk_signal.signal_type,
                trade_date=date.today(),
            ),
        ])
        self.session.commit()

        self.tmp = TemporaryDirectory()
        dist = Path(self.tmp.name)
        (dist / "assets").mkdir()
        (dist / "index.html").write_text("<html>vue-app</html>", encoding="utf-8")
        (dist / "assets" / "app.js").write_text("console.log('ok')", encoding="utf-8")

        self.app = create_app(dist)

        def override_session():
            yield self.session

        self.app.dependency_overrides[get_db_session] = override_session
        self.client = TestClient(self.app)

    def tearDown(self):
        self.client.close()
        self.session.close()
        self.engine.dispose()
        self.tmp.cleanup()

    def test_health_reports_database_status(self):
        response = self.client.get("/api/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")
        self.assertEqual(response.json()["database"]["status"], "ok")

    def test_signal_list_supports_filters_and_pagination(self):
        response = self.client.get("/api/signals?days=7&level=2&limit=1&offset=0")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["total"], 2)
        self.assertEqual(payload["limit"], 1)
        self.assertEqual(len(payload["items"]), 1)
        self.assertEqual(payload["items"][0]["title"], "指数回落")

        filtered = self.client.get("/api/signals?monitor=hk_shock&type=hk_index_down")
        self.assertEqual(filtered.status_code, 200)
        self.assertEqual(filtered.json()["total"], 1)
        self.assertEqual(filtered.json()["items"][0]["level"], 3)

    def test_signal_detail_and_missing_signal(self):
        signal_id = self.session.query(SignalEvent.id).order_by(SignalEvent.id).first()[0]

        response = self.client.get(f"/api/signals/{signal_id}")
        missing = self.client.get("/api/signals/99999")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], signal_id)
        self.assertEqual(response.json()["push"]["title"], "盘中风险提示")
        self.assertEqual(response.json()["actions"][0]["decision"], "act")
        self.assertEqual(response.json()["trades"][0]["symbol"], "s_sh000001")
        self.assertEqual(missing.status_code, 404)

    def test_metadata_endpoints_supply_real_filter_options(self):
        monitors = self.client.get("/api/monitors")
        signal_types = self.client.get("/api/signal-types?monitor=pulse")

        self.assertEqual(monitors.status_code, 200)
        self.assertEqual(len(monitors.json()["items"]), 2)
        self.assertEqual(monitors.json()["items"][0]["display_name"], "盘中脉搏")
        self.assertEqual(signal_types.status_code, 200)
        self.assertEqual(len(signal_types.json()["items"]), 1)
        self.assertEqual(signal_types.json()["items"][0]["signal_type"], "pulse_index_down")

    def test_push_trade_and_stats_read_models(self):
        pushes = self.client.get("/api/pushes?days=7&level=2&limit=1")
        trades = self.client.get("/api/trades?status=open&limit=1")
        stats = self.client.get("/api/stats/summary?days=1")
        invalid_trade_filter = self.client.get("/api/trades?status=pending")

        self.assertEqual(pushes.status_code, 200)
        self.assertEqual(pushes.json()["total"], 1)
        self.assertEqual(pushes.json()["items"][0]["context"], {"source": "test"})
        self.assertEqual(trades.status_code, 200)
        self.assertEqual(trades.json()["total"], 1)
        self.assertEqual(trades.json()["items"][0]["signal_event_id"], 1)
        self.assertEqual(stats.status_code, 200)
        self.assertEqual(stats.json()["signals"], 2)
        self.assertEqual(stats.json()["pushes"], 1)
        self.assertEqual(stats.json()["open_trades"], 1)
        self.assertEqual(stats.json()["pending_outcomes"], 1)
        self.assertEqual(invalid_trade_filter.status_code, 422)

    def test_write_api_is_restricted_to_explicit_research_workflows(self):
        schema = self.client.get("/openapi.json").json()
        writes = {
            (path, method)
            for path, operations in schema["paths"].items()
            if path.startswith("/api/")
            for method in operations
            if method in {"post", "put", "patch", "delete"}
        }

        self.assertEqual(writes, {
            ("/api/signals/{signal_id}/actions", "post"),
            ("/api/signals/{signal_id}/notes", "post"),
            ("/api/trades", "post"),
            ("/api/trades/{trade_id}/close", "patch"),
            ("/api/reviews/generate", "post"),
        })

    def test_signal_research_writes_are_idempotent_and_visible(self):
        signal_id = self.session.query(SignalEvent.id).order_by(SignalEvent.id).first()[0]

        action = self.client.post(
            f"/api/signals/{signal_id}/actions",
            json={"decision": "watch", "reason": "等待确认"},
        )
        repeated_action = self.client.post(
            f"/api/signals/{signal_id}/actions",
            json={"decision": "watch", "reason": "等待确认"},
        )
        note = self.client.post(
            f"/api/signals/{signal_id}/notes",
            json={"body": "  关注午后量能  "},
        )
        repeated_note = self.client.post(
            f"/api/signals/{signal_id}/notes",
            json={"body": "关注午后量能"},
        )
        detail = self.client.get(f"/api/signals/{signal_id}").json()

        self.assertEqual(action.status_code, 201)
        self.assertTrue(action.json()["created"])
        self.assertEqual(repeated_action.status_code, 200)
        self.assertFalse(repeated_action.json()["created"])
        self.assertEqual(note.status_code, 201)
        self.assertEqual(repeated_note.status_code, 200)
        self.assertEqual(len([row for row in detail["actions"] if row["decision"] == "watch"]), 1)
        self.assertEqual(detail["notes"][0]["body"], "关注午后量能")

    def test_trade_create_link_close_and_request_id_conflict(self):
        signal_id = self.session.query(SignalEvent.id).order_by(SignalEvent.id).first()[0]
        payload = {
            "request_id": "web-test-trade-001",
            "symbol": "sh600000",
            "name": "浦发银行",
            "entry_price": 10.0,
            "qty": 100,
            "strategy": "signal-follow",
            "signal_event_id": signal_id,
            "entry_reason": "信号确认",
        }

        created = self.client.post("/api/trades", json=payload)
        repeated = self.client.post("/api/trades", json=payload)
        conflict = self.client.post("/api/trades", json={**payload, "strategy": "different"})
        trade_id = created.json()["id"]
        closed = self.client.patch(
            f"/api/trades/{trade_id}/close",
            json={"close_price": 10.5, "close_reason": "目标达成"},
        )
        repeated_close = self.client.patch(
            f"/api/trades/{trade_id}/close",
            json={"close_price": 10.6},
        )
        detail = self.client.get(f"/api/signals/{signal_id}").json()

        self.assertEqual(created.status_code, 201)
        self.assertEqual(repeated.status_code, 200)
        self.assertEqual(repeated.json()["id"], trade_id)
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(closed.status_code, 200)
        self.assertEqual(closed.json()["status"], "closed")
        self.assertAlmostEqual(closed.json()["pnl"], 50.0)
        self.assertEqual(repeated_close.status_code, 409)
        self.assertIn(trade_id, [row["id"] for row in detail["trades"]])

    def test_write_token_is_optional_but_enforced_when_configured(self):
        signal_id = self.session.query(SignalEvent.id).order_by(SignalEvent.id).first()[0]
        with patch.dict("os.environ", {"MARKET_WEB_TOKEN": "local-secret"}):
            denied = self.client.post(
                f"/api/signals/{signal_id}/notes",
                json={"body": "受保护笔记"},
            )
            allowed = self.client.post(
                f"/api/signals/{signal_id}/notes",
                headers={"X-Market-Token": "local-secret"},
                json={"body": "受保护笔记"},
            )

        self.assertEqual(denied.status_code, 401)
        self.assertEqual(allowed.status_code, 201)

    def test_review_generation_read_and_markdown_export(self):
        trade = self.session.query(PaperTrade).filter(PaperTrade.status == "open").first()
        close = self.client.patch(
            f"/api/trades/{trade.id}/close",
            json={"close_price": 3510, "close_reason": "复盘测试"},
        )
        generated = self.client.post("/api/reviews/generate", json={"period_type": "week"})
        payload = generated.json()
        fetched = self.client.get(f"/api/reviews/week/{payload['period_key']}")
        markdown = self.client.get(
            f"/api/reviews/week/{payload['period_key']}/markdown"
        )

        self.assertEqual(close.status_code, 200)
        self.assertEqual(generated.status_code, 200)
        self.assertGreaterEqual(payload["trade_count"], 1)
        self.assertIn("decision_distribution", payload)
        self.assertEqual(fetched.status_code, 200)
        self.assertEqual(markdown.status_code, 200)
        self.assertIn("attachment;", markdown.headers["content-disposition"])
        self.assertIn("# 周度复盘", markdown.text)

    def test_system_status_is_operational_and_sanitized(self):
        response = self.client.get("/api/system/status")
        serialized = response.text.lower()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["healthy"])
        self.assertIn("signal_note", [row["table"] for row in response.json()["tables"]])
        self.assertIn("monitors", response.json())
        self.assertNotIn("api_key", serialized)
        self.assertNotIn("secret", serialized)

    def test_complete_research_workflow(self):
        signal_id = self.session.query(SignalEvent.id).order_by(SignalEvent.id).first()[0]
        self.assertEqual(self.client.get(f"/api/signals/{signal_id}").status_code, 200)
        self.assertEqual(self.client.post(
            f"/api/signals/{signal_id}/actions",
            json={"decision": "act", "reason": "端到端确认"},
        ).status_code, 201)
        self.assertEqual(self.client.post(
            f"/api/signals/{signal_id}/notes", json={"body": "端到端批注"},
        ).status_code, 201)
        trade = self.client.post("/api/trades", json={
            "request_id": "workflow-trade-001",
            "symbol": "s_sh000001",
            "entry_price": 3500,
            "qty": 1,
            "signal_event_id": signal_id,
        })
        self.assertEqual(trade.status_code, 201)
        self.assertEqual(self.client.patch(
            f"/api/trades/{trade.json()['id']}/close", json={"close_price": 3510},
        ).status_code, 200)

        for period_type in ("week", "month"):
            review = self.client.post(
                "/api/reviews/generate", json={"period_type": period_type},
            )
            self.assertEqual(review.status_code, 200)
            period_key = review.json()["period_key"]
            export = self.client.get(
                f"/api/reviews/{period_type}/{period_key}/markdown"
            )
            self.assertEqual(export.status_code, 200)
            self.assertIn("复盘", export.text)

        detail = self.client.get(f"/api/signals/{signal_id}").json()
        self.assertIn("端到端批注", [note["body"] for note in detail["notes"]])
        self.assertIn(trade.json()["id"], [row["id"] for row in detail["trades"]])
        self.assertTrue(self.client.get("/api/system/status").json()["healthy"])

    def test_vue_history_fallback_does_not_mask_unknown_api_routes(self):
        root = self.client.get("/")
        nested = self.client.get("/signals/42")
        asset = self.client.get("/assets/app.js")
        unknown_api = self.client.get("/api/not-a-route")

        self.assertIn("vue-app", root.text)
        self.assertIn("vue-app", nested.text)
        self.assertIn("console.log", asset.text)
        self.assertEqual(unknown_api.status_code, 404)


if __name__ == "__main__":
    unittest.main()
