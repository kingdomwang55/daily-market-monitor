"""market_snapshot 相关操作"""
from datetime import datetime, timezone, timedelta
from typing import Optional, Iterable

from sqlalchemy import select, desc
from sqlalchemy.orm import Session

from ..models import MarketSnapshot


SHANGHAI = timezone(timedelta(hours=8))


def _trade_date(ts_utc: datetime):
    return ts_utc.replace(tzinfo=timezone.utc).astimezone(SHANGHAI).date()


class MarketSnapshotRepository:
    def __init__(self, session: Session):
        self.s = session

    def bulk_insert(
        self,
        rows: Iterable[dict],
        source: str = "sina",
        ts: Optional[datetime] = None,
    ) -> int:
        """批量落库

        rows: [{"symbol":"s_sh000001","price":...,"pct":...,"prev_close":..., "raw": {...}}, ...]
        """
        ts = ts or datetime.utcnow()
        td = _trade_date(ts)
        objs = []
        for r in rows:
            objs.append(MarketSnapshot(
                ts=ts,
                trade_date=td,
                symbol=r["symbol"],
                price=r.get("price"),
                prev_close=r.get("prev_close"),
                pct=r.get("pct"),
                amount=r.get("amount"),
                volume=r.get("volume"),
                stage=r.get("stage"),
                source=source,
                raw_json=r.get("raw"),
            ))
        self.s.add_all(objs)
        self.s.flush()
        return len(objs)

    # 别名：与调用方保持兼容
    bulk_create = bulk_insert

    def latest(self, symbol: str) -> Optional[MarketSnapshot]:
        q = select(MarketSnapshot).where(MarketSnapshot.symbol == symbol).order_by(desc(MarketSnapshot.ts)).limit(1)
        return self.s.execute(q).scalar_one_or_none()
