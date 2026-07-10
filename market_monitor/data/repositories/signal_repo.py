"""signal_event 相关操作"""
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from ..models import SignalEvent


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
