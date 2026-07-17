"""Persist structured Signal objects."""
from __future__ import annotations

from typing import Iterable

from ..data.repositories import SignalEventRepository
from .types import Signal


def persist_signals(session, signals: Iterable[Signal]):
    """Persist signals into signal_event rows and return ORM rows."""

    repo = SignalEventRepository(session)
    rows = []
    for signal in signals:
        metrics = dict(signal.metrics or {})
        if signal.title:
            metrics.setdefault("title", signal.title)
        if signal.summary:
            metrics.setdefault("summary", signal.summary)
        metrics["direction"] = signal.direction
        if signal.symbols:
            metrics.setdefault("symbols", signal.symbols)
        if signal.evidence:
            metrics.setdefault("evidence", signal.evidence)
        if signal.dedup_key:
            metrics.setdefault("dedup_key", signal.dedup_key)
        if signal.status:
            metrics.setdefault("status", signal.status)

        rows.append(repo.create(
            monitor=signal.monitor,
            signal_type=signal.signal_type,
            symbol=signal.symbol,
            level=signal.level,
            metrics=metrics,
            push_log_id=signal.push_log_id,
            ts=signal.ts,
        ))
    return rows
