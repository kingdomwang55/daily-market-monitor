"""Signal outcome verification helpers."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from ..models import SignalEvent, SignalOutcome, SymbolOhlcDaily


class SignalOutcomeRepository:
    """Backfill and query forward returns for detected signals."""

    def __init__(self, session: Session):
        self.s = session

    def by_signal(self, signal_event_id: int) -> Optional[SignalOutcome]:
        q = select(SignalOutcome).where(SignalOutcome.signal_event_id == signal_event_id)
        return self.s.execute(q).scalars().first()

    def recent(self, *, days: Optional[int] = 30, limit: int = 100) -> list[SignalOutcome]:
        q = select(SignalOutcome)
        if days:
            since = datetime.utcnow().date() - timedelta(days=days)
            q = q.where(SignalOutcome.trade_date >= since)
        q = q.order_by(desc(SignalOutcome.trade_date), desc(SignalOutcome.id)).limit(limit)
        return list(self.s.execute(q).scalars().all())

    def backfill_recent(self, *, days: int = 30, limit: int = 200) -> list[SignalOutcome]:
        since = datetime.utcnow() - timedelta(days=days)
        q = (
            select(SignalEvent)
            .where(SignalEvent.ts >= since)
            .where(SignalEvent.symbol.is_not(None))
            .order_by(desc(SignalEvent.ts))
            .limit(limit)
        )
        outcomes = []
        for signal in self.s.execute(q).scalars().all():
            outcome = self.upsert_for_signal(signal)
            if outcome is not None:
                outcomes.append(outcome)
        return outcomes

    def upsert_for_signal(self, signal: SignalEvent) -> Optional[SignalOutcome]:
        if not signal.symbol:
            return None

        rows = self._future_ohlc_rows(signal.symbol, signal.trade_date, limit=5)
        if not rows:
            return None

        direction = self._predicted_direction(signal)
        t1_pct = self._pct_at(rows, 1)
        t3_pct = self._pct_at(rows, 3)
        t5_pct = self._pct_at(rows, 5)

        row = self.by_signal(signal.id)
        if row is None:
            row = SignalOutcome(
                signal_event_id=signal.id,
                signal_type=signal.signal_type,
                trade_date=signal.trade_date,
            )
            self.s.add(row)

        row.signal_type = signal.signal_type
        row.trade_date = signal.trade_date
        row.predicted_direction = direction
        row.t1_pct = t1_pct
        row.t3_pct = t3_pct
        row.t5_pct = t5_pct
        row.t1_hit = self._hit(direction, t1_pct)
        row.t3_hit = self._hit(direction, t3_pct)
        row.verified_at = datetime.utcnow()
        self.s.flush()
        return row

    def _future_ohlc_rows(self, symbol: str, trade_date, *, limit: int) -> list[SymbolOhlcDaily]:
        q = (
            select(SymbolOhlcDaily)
            .where(SymbolOhlcDaily.symbol == symbol)
            .where(SymbolOhlcDaily.trade_date > trade_date)
            .order_by(SymbolOhlcDaily.trade_date)
            .limit(limit)
        )
        return list(self.s.execute(q).scalars().all())

    @staticmethod
    def _pct_at(rows: list[SymbolOhlcDaily], n: int) -> Optional[float]:
        if len(rows) < n:
            return None
        return rows[n - 1].pct

    @staticmethod
    def _predicted_direction(signal: SignalEvent) -> Optional[int]:
        metrics = signal.metrics_json or {}
        if isinstance(metrics, dict) and metrics.get("direction") is not None:
            try:
                return int(metrics["direction"])
            except (TypeError, ValueError):
                return None
        return None

    @staticmethod
    def _hit(direction: Optional[int], pct: Optional[float]) -> Optional[bool]:
        if direction is None or pct is None:
            return None
        if direction > 0:
            return pct > 0
        if direction < 0:
            return pct < 0
        return abs(pct) < 0.5


def signal_outcome_to_dict(row: SignalOutcome) -> dict:
    return {
        "id": row.id,
        "signal_event_id": row.signal_event_id,
        "signal_type": row.signal_type,
        "trade_date": row.trade_date.isoformat() if row.trade_date else None,
        "predicted_direction": row.predicted_direction,
        "t1_pct": row.t1_pct,
        "t3_pct": row.t3_pct,
        "t5_pct": row.t5_pct,
        "t1_hit": row.t1_hit,
        "t3_hit": row.t3_hit,
        "verified_at": row.verified_at.isoformat() + "Z" if row.verified_at else None,
    }
