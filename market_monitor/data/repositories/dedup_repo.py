"""alert_dedup 相关操作（替代 JSON state 文件）"""
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import AlertDedup


SHANGHAI = timezone(timedelta(hours=8))


def _trade_date(ts_utc: datetime):
    return ts_utc.replace(tzinfo=timezone.utc).astimezone(SHANGHAI).date()


class AlertDedupRepository:
    def __init__(self, session: Session):
        self.s = session

    def seen(self, monitor: str, dedup_key: str) -> bool:
        q = select(AlertDedup).where(
            AlertDedup.monitor == monitor,
            AlertDedup.dedup_key == dedup_key,
        )
        return self.s.execute(q).scalar_one_or_none() is not None

    def mark(self, monitor: str, dedup_key: str, ts: Optional[datetime] = None) -> AlertDedup:
        ts = ts or datetime.utcnow()
        # 存在则返回原记录，不重复写
        existing = self.s.get(AlertDedup, (monitor, dedup_key))
        if existing:
            return existing
        row = AlertDedup(
            monitor=monitor,
            dedup_key=dedup_key,
            first_seen=ts,
            trade_date=_trade_date(ts),
        )
        self.s.add(row)
        self.s.flush()
        return row
