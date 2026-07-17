"""Read-side helpers for structured signals."""
from __future__ import annotations

from sqlalchemy.exc import SQLAlchemyError

from ..data.repositories import SignalEventRepository
from ..data.seeds import SIGNAL_TYPES
from .types import signal_event_to_dict


def _rollback_quietly(session) -> None:
    try:
        session.rollback()
    except Exception:
        pass


def list_signal_types(session=None, monitor: str | None = None) -> list[dict]:
    """Return registered signal types, falling back to seed metadata."""

    if session is not None:
        try:
            rows = SignalEventRepository(session).signal_types(monitor=monitor)
            if rows:
                return [
                    {
                        "signal_type": r.signal_type,
                        "monitor": r.monitor,
                        "display_name": r.display_name,
                        "direction": r.direction,
                        "description": r.description,
                    }
                    for r in rows
                ]
        except SQLAlchemyError:
            _rollback_quietly(session)
            pass

    result = []
    for signal_type, mon, display, direction, description in SIGNAL_TYPES:
        if monitor and mon != monitor:
            continue
        result.append({
            "signal_type": signal_type,
            "monitor": mon,
            "display_name": display,
            "direction": direction,
            "description": description,
        })
    return result


def list_signals(
    session,
    *,
    monitor: str | None = None,
    signal_type: str | None = None,
    days: int | None = 7,
    min_level: int = 0,
    limit: int = 50,
) -> list[dict]:
    try:
        rows = SignalEventRepository(session).recent(
            monitor=monitor,
            signal_type=signal_type,
            days=days,
            min_level=min_level,
            limit=limit,
        )
    except SQLAlchemyError:
        _rollback_quietly(session)
        return []
    return [signal_event_to_dict(row) for row in rows]


def get_signal(session, signal_id: int) -> dict | None:
    try:
        row = SignalEventRepository(session).by_id(signal_id)
    except SQLAlchemyError:
        _rollback_quietly(session)
        return None
    if row is None:
        return None
    return signal_event_to_dict(row)
