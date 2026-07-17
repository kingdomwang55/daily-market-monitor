"""Repository 层：业务代码只通过这一层访问 DB

所有 SQL 都在这里，业务代码永远不 import SQLAlchemy。
未来切 PG/TimescaleDB/RawSQL，只改本层。
"""
from .push_repo import PushLogRepository
from .snapshot_repo import MarketSnapshotRepository
from .signal_repo import SignalEventRepository
from .dedup_repo import AlertDedupRepository
from .stats_repo import StatsRepository
from .trade_repo import (
    PaperTradeRepository,
    TradeSignalLinkRepository,
    TradeReviewRepository,
)
from .outcome_repo import SignalOutcomeRepository

__all__ = [
    "PushLogRepository",
    "MarketSnapshotRepository",
    "SignalEventRepository",
    "AlertDedupRepository",
    "StatsRepository",
    "PaperTradeRepository",
    "TradeSignalLinkRepository",
    "TradeReviewRepository",
    "SignalOutcomeRepository",
]
