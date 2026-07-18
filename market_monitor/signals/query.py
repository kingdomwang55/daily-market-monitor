"""Read-side helpers for structured signals."""
from __future__ import annotations

from sqlalchemy.exc import SQLAlchemyError

from ..data.repositories import SignalEventRepository
from ..data.repositories import (
    PaperTradeRepository,
    PushLogRepository,
    SignalNoteRepository,
    TradeSignalLinkRepository,
)
from ..data.serializers import (
    paper_trade_to_dict,
    push_log_to_dict,
    signal_note_to_dict,
    trade_signal_link_to_dict,
)
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
    push_log_id: int | None = None,
    days: int | None = 7,
    min_level: int = 0,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    try:
        rows = SignalEventRepository(session).recent(
            monitor=monitor,
            signal_type=signal_type,
            push_log_id=push_log_id,
            days=days,
            min_level=min_level,
            limit=limit,
            offset=offset,
        )
    except SQLAlchemyError:
        _rollback_quietly(session)
        return []
    return [signal_event_to_dict(row) for row in rows]


def count_signals(
    session,
    *,
    monitor: str | None = None,
    signal_type: str | None = None,
    push_log_id: int | None = None,
    days: int | None = 7,
    min_level: int = 0,
) -> int:
    try:
        return SignalEventRepository(session).count(
            monitor=monitor,
            signal_type=signal_type,
            push_log_id=push_log_id,
            days=days,
            min_level=min_level,
        )
    except SQLAlchemyError:
        _rollback_quietly(session)
        return 0


def get_signal(session, signal_id: int) -> dict | None:
    try:
        row = SignalEventRepository(session).by_id(signal_id)
    except SQLAlchemyError:
        _rollback_quietly(session)
        return None
    if row is None:
        return None
    return signal_event_to_dict(row)


def get_signal_detail(session, signal_id: int) -> dict | None:
    signal = get_signal(session, signal_id)
    if signal is None:
        return None

    push = None
    if signal.get("push_log_id"):
        push_row = PushLogRepository(session).by_id(signal["push_log_id"])
        if push_row is not None:
            push = push_log_to_dict(push_row)

    link_rows = TradeSignalLinkRepository(session).by_signal(signal_id)
    trade_repository = PaperTradeRepository(session)
    trade_rows = trade_repository.by_signal(signal_id)
    known_trade_ids = {row.id for row in trade_rows}
    for link in link_rows:
        if link.paper_trade_id is None or link.paper_trade_id in known_trade_ids:
            continue
        trade = trade_repository.by_id(link.paper_trade_id)
        if trade is not None:
            trade_rows.append(trade)
            known_trade_ids.add(trade.id)

    note_rows = SignalNoteRepository(session).by_signal(signal_id)
    signal["push"] = push
    signal["actions"] = [trade_signal_link_to_dict(row) for row in link_rows]
    signal["notes"] = [signal_note_to_dict(row) for row in note_rows]
    signal["trades"] = [paper_trade_to_dict(row) for row in trade_rows]
    return signal
