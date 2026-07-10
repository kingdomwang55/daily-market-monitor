"""push_log 相关操作"""
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy import select, desc
from sqlalchemy.orm import Session

from ..models import PushLog


SHANGHAI = timezone(timedelta(hours=8))


def _trade_date(ts_utc: datetime):
    """UTC datetime → Asia/Shanghai date"""
    return ts_utc.replace(tzinfo=timezone.utc).astimezone(SHANGHAI).date()


class PushLogRepository:
    def __init__(self, session: Session):
        self.s = session

    def create(
        self,
        monitor: str,
        message: str,
        *,
        scenario: Optional[str] = None,
        max_level: int = 0,
        title: Optional[str] = None,
        context: Optional[dict] = None,
        sent_ok: Optional[bool] = None,
        error: Optional[str] = None,
        ts: Optional[datetime] = None,
    ) -> PushLog:
        ts = ts or datetime.utcnow()
        row = PushLog(
            ts=ts,
            trade_date=_trade_date(ts),
            monitor=monitor,
            scenario=scenario,
            max_level=max_level,
            title=title,
            message=message,
            context_json=context,
            sent_ok=sent_ok,
            error=error,
        )
        self.s.add(row)
        self.s.flush()   # 拿到 id
        return row

    def recent(self, monitor: Optional[str] = None, limit: int = 20,
               days: Optional[int] = None, min_level: int = 0):
        q = select(PushLog)
        if monitor:
            q = q.where(PushLog.monitor == monitor)
        if min_level:
            q = q.where(PushLog.max_level >= min_level)
        if days:
            since = datetime.utcnow() - timedelta(days=days)
            q = q.where(PushLog.ts >= since)
        q = q.order_by(desc(PushLog.ts)).limit(limit)
        return self.s.execute(q).scalars().all()

    def by_id(self, pid: int) -> Optional[PushLog]:
        return self.s.get(PushLog, pid)
