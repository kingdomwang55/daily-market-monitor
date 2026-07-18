"""统计查询（daily_summary 等派生视图）"""
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session

from ..models import PaperTrade, PushLog, SignalEvent, SignalOutcome


class StatsRepository:
    def __init__(self, session: Session):
        self.s = session

    def push_count_by_day(self, day: date, monitor: Optional[str] = None) -> int:
        q = select(func.count(PushLog.id)).where(PushLog.trade_date == day)
        if monitor:
            q = q.where(PushLog.monitor == monitor)
        return int(self.s.execute(q).scalar() or 0)

    def top_signal_types(self, days: int = 30, limit: int = 20):
        q = (
            select(SignalEvent.signal_type, func.count(SignalEvent.id).label("n"))
            .group_by(SignalEvent.signal_type)
            .order_by(func.count(SignalEvent.id).desc())
            .limit(limit)
        )
        return self.s.execute(q).all()

    # ==================================================
    # CLI 专用辅助接口
    # ==================================================
    def monitor_stats(self, days: int = 30):
        """按 monitor 聚合推送次数 / 平均级别 / 最大级别"""
        since = datetime.utcnow() - timedelta(days=days)
        q = (
            select(
                PushLog.monitor,
                func.count(PushLog.id).label("count"),
                func.avg(PushLog.max_level).label("avg_level"),
                func.max(PushLog.max_level).label("max_level"),
            )
            .where(PushLog.ts >= since)
            .group_by(PushLog.monitor)
            .order_by(func.count(PushLog.id).desc())
        )
        rows = self.s.execute(q).all()
        return [
            {
                "monitor": r.monitor,
                "count": int(r.count or 0),
                "avg_level": round(float(r.avg_level or 0), 2),
                "max_level": int(r.max_level or 0),
            }
            for r in rows
        ]

    def signal_frequency(self, days: int = 30, limit: int = 30):
        """最近 N 天信号频率"""
        since = datetime.utcnow() - timedelta(days=days)
        q = (
            select(
                SignalEvent.signal_type,
                func.count(SignalEvent.id).label("count"),
            )
            .where(SignalEvent.ts >= since)
            .group_by(SignalEvent.signal_type)
            .order_by(func.count(SignalEvent.id).desc())
            .limit(limit)
        )
        rows = self.s.execute(q).all()
        return [{"signal_type": r.signal_type, "count": int(r.count or 0)} for r in rows]

    def web_summary(self, days: int = 7) -> dict:
        """Compact read model for the Web Today page."""
        since = datetime.utcnow() - timedelta(days=days)
        signal_filter = SignalEvent.ts >= since
        push_filter = PushLog.ts >= since
        trade_filter = PaperTrade.entry_at >= since

        signal_count = self.s.execute(
            select(func.count()).select_from(SignalEvent).where(signal_filter)
        ).scalar_one()
        push_count = self.s.execute(
            select(func.count()).select_from(PushLog).where(push_filter)
        ).scalar_one()
        trade_count = self.s.execute(
            select(func.count()).select_from(PaperTrade).where(trade_filter)
        ).scalar_one()
        max_level = self.s.execute(
            select(func.max(SignalEvent.level)).where(signal_filter)
        ).scalar_one()
        open_trades = self.s.execute(
            select(func.count()).select_from(PaperTrade).where(PaperTrade.status == "open")
        ).scalar_one()
        pending_outcomes = self.s.execute(
            select(func.count())
            .select_from(SignalEvent)
            .where(
                signal_filter,
                ~exists().where(SignalOutcome.signal_event_id == SignalEvent.id),
            )
        ).scalar_one()

        return {
            "days": days,
            "signals": int(signal_count),
            "pushes": int(push_count),
            "trades": int(trade_count),
            "max_signal_level": int(max_level or 0),
            "open_trades": int(open_trades),
            "pending_outcomes": int(pending_outcomes),
        }
