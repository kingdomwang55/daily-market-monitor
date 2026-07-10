"""统计查询（daily_summary 等派生视图）"""
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from ..models import PushLog, SignalEvent


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
