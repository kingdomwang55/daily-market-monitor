"""Signal domain types.

This module is intentionally small: Phase 1 establishes a stable shape for
OpenClaw/CLI consumption before monitors are migrated into detectors.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Any, Optional


@dataclass(frozen=True)
class Signal:
    """A structured market signal detected by a rule or AI helper."""

    monitor: str
    signal_type: str
    title: str = ""
    symbol: Optional[str] = None
    symbols: list[str] = field(default_factory=list)
    direction: int = 0
    level: int = 0
    summary: str = ""
    metrics: dict[str, Any] = field(default_factory=dict)
    evidence: dict[str, Any] = field(default_factory=dict)
    dedup_key: Optional[str] = None
    status: str = "detected"
    ts: Optional[datetime] = None
    push_log_id: Optional[int] = None


@dataclass(frozen=True)
class SignalContext:
    """Context shared by future detectors."""

    now: datetime
    config: Any = None
    market_stage: Optional[str] = None
    quotes: dict[str, Any] = field(default_factory=dict)
    klines: dict[str, Any] = field(default_factory=dict)
    positions: dict[str, Any] = field(default_factory=dict)
    recent_signals: list[Signal] = field(default_factory=list)
    raw_payloads: dict[str, Any] = field(default_factory=dict)


def _iso(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat() + ("Z" if value.tzinfo is None else "")
    if isinstance(value, date):
        return value.isoformat()
    return value


def signal_event_to_dict(row) -> dict[str, Any]:
    """Serialize a SignalEvent ORM row into the public CLI JSON shape."""

    metrics = row.metrics_json or {}
    symbols = []
    if row.symbol:
        symbols.append(row.symbol)
    extra_symbols = metrics.get("symbols") if isinstance(metrics, dict) else None
    if isinstance(extra_symbols, list):
        for symbol in extra_symbols:
            if symbol not in symbols:
                symbols.append(symbol)

    title = None
    direction = None
    if isinstance(metrics, dict):
        title = metrics.get("title") or metrics.get("summary")
        direction = metrics.get("direction")

    return {
        "id": row.id,
        "ts": _iso(row.ts),
        "trade_date": _iso(row.trade_date),
        "monitor": row.monitor,
        "signal_type": row.signal_type,
        "symbol": row.symbol,
        "symbols": symbols,
        "direction": direction,
        "level": row.level,
        "title": title or row.signal_type,
        "status": "pushed" if row.push_log_id else "detected",
        "metrics": metrics,
        "push_log_id": row.push_log_id,
        "outcome": None,
    }
