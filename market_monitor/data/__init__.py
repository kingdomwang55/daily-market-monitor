"""market-monitor 数据层

分层：
- Meta   : monitor_registry / symbol_registry / signal_type_registry
- Raw    : market_snapshot
- Event  : push_log / signal_event / alert_dedup
- Derived: daily_summary / signal_outcome / symbol_ohlc_daily

技术栈：SQLAlchemy 2.0 + Alembic
DB URL 通过环境变量 MARKET_DB_URL 覆盖，默认 SQLite。
"""
from .database import get_engine, get_session, init_db, db_info
from .models import (
    MonitorRegistry,
    SymbolRegistry,
    SignalTypeRegistry,
    MarketSnapshot,
    PushLog,
    SignalEvent,
    AlertDedup,
    DailySummary,
    SignalOutcome,
    SymbolOhlcDaily,
    PaperTrade,
    TradeSignalLink,
    SignalNote,
    TradeReview,
)

__all__ = [
    "get_engine",
    "get_session",
    "init_db",
    "MonitorRegistry",
    "SymbolRegistry",
    "SignalTypeRegistry",
    "MarketSnapshot",
    "PushLog",
    "SignalEvent",
    "AlertDedup",
    "DailySummary",
    "SignalOutcome",
    "SymbolOhlcDaily",
    "PaperTrade",
    "TradeSignalLink",
    "SignalNote",
    "TradeReview",
]
