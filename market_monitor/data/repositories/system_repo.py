"""Read models for local Web system status."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import (
    AlertDedup,
    DailySummary,
    MarketSnapshot,
    MonitorRegistry,
    PaperTrade,
    PushLog,
    SignalEvent,
    SignalNote,
    SignalOutcome,
    SignalTypeRegistry,
    SymbolOhlcDaily,
    SymbolRegistry,
    TradeReview,
    TradeSignalLink,
)


class SystemRepository:
    TABLES = (
        (MonitorRegistry, "monitor_registry"),
        (SymbolRegistry, "symbol_registry"),
        (SignalTypeRegistry, "signal_type_registry"),
        (MarketSnapshot, "market_snapshot"),
        (PushLog, "push_log"),
        (SignalEvent, "signal_event"),
        (SignalNote, "signal_note"),
        (AlertDedup, "alert_dedup"),
        (DailySummary, "daily_summary"),
        (SignalOutcome, "signal_outcome"),
        (SymbolOhlcDaily, "symbol_ohlc_daily"),
        (PaperTrade, "paper_trade"),
        (TradeSignalLink, "trade_signal_link"),
        (TradeReview, "trade_review"),
    )

    def __init__(self, session: Session):
        self.s = session

    def monitor_statuses(self) -> list[dict]:
        rows = self.s.execute(
            select(
                MonitorRegistry,
                func.max(PushLog.ts).label("last_push_at"),
                func.count(PushLog.id).label("push_count"),
            )
            .outerjoin(PushLog, PushLog.monitor == MonitorRegistry.name)
            .group_by(MonitorRegistry.name)
            .order_by(MonitorRegistry.category, MonitorRegistry.name)
        ).all()
        return [
            {
                "name": monitor.name,
                "display_name": monitor.display_name,
                "category": monitor.category,
                "enabled": monitor.enabled,
                "description": monitor.description,
                "last_push_at": last_push_at,
                "push_count": int(push_count or 0),
            }
            for monitor, last_push_at, push_count in rows
        ]

    def table_counts(self) -> list[dict]:
        return [
            {
                "table": name,
                "rows": int(
                    self.s.execute(select(func.count()).select_from(model)).scalar_one()
                ),
            }
            for model, name in self.TABLES
        ]
