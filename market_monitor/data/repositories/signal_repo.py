"""signal_event 相关操作"""
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from ..models import SignalEvent, SignalTypeRegistry


SHANGHAI = timezone(timedelta(hours=8))


def _trade_date(ts_utc: datetime):
    return ts_utc.replace(tzinfo=timezone.utc).astimezone(SHANGHAI).date()


class SignalEventRepository:
    def __init__(self, session: Session):
        self.s = session

    def create(
        self,
        monitor: str,
        signal_type: str,
        *,
        symbol: Optional[str] = None,
        level: Optional[int] = None,
        hk_avg_pct: Optional[float] = None,
        a_avg_pct: Optional[float] = None,
        metrics: Optional[dict] = None,
        push_log_id: Optional[int] = None,
        ts: Optional[datetime] = None,
    ) -> SignalEvent:
        ts = ts or datetime.utcnow()
        row = SignalEvent(
            ts=ts,
            trade_date=_trade_date(ts),
            monitor=monitor,
            signal_type=signal_type,
            symbol=symbol,
            level=level,
            hk_avg_pct=hk_avg_pct,
            a_avg_pct=a_avg_pct,
            metrics_json=metrics,
            push_log_id=push_log_id,
        )
        self.s.add(row)
        self.s.flush()
        return row

    def by_id(self, signal_id: int) -> Optional[SignalEvent]:
        return self.s.get(SignalEvent, signal_id)

    def recent(
        self,
        *,
        monitor: Optional[str] = None,
        signal_type: Optional[str] = None,
        push_log_id: Optional[int] = None,
        days: Optional[int] = None,
        min_level: int = 0,
        limit: int = 50,
    ):
        q = select(SignalEvent)
        if monitor:
            q = q.where(SignalEvent.monitor == monitor)
        if signal_type:
            q = q.where(SignalEvent.signal_type == signal_type)
        if push_log_id is not None:
            q = q.where(SignalEvent.push_log_id == push_log_id)
        if min_level:
            q = q.where(SignalEvent.level >= min_level)
        if days:
            since = datetime.utcnow() - timedelta(days=days)
            q = q.where(SignalEvent.ts >= since)
        q = q.order_by(desc(SignalEvent.ts)).limit(limit)
        return self.s.execute(q).scalars().all()

    def signal_types(self, monitor: Optional[str] = None):
        q = select(SignalTypeRegistry)
        if monitor:
            q = q.where(SignalTypeRegistry.monitor == monitor)
        q = q.order_by(SignalTypeRegistry.monitor, SignalTypeRegistry.signal_type)
        return self.s.execute(q).scalars().all()
