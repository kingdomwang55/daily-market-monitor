"""Signal read models and research annotation endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from ...data.repositories import (
    PaperTradeRepository,
    SignalEventRepository,
    SignalNoteRepository,
    TradeSignalLinkRepository,
)
from ...data.serializers import (
    signal_note_to_dict,
    trade_signal_link_to_dict,
)
from ...signals.query import count_signals, get_signal_detail, list_signals
from ..deps import get_db_session
from ..schemas import SignalActionCreate, SignalNoteCreate
from ..security import require_write_access


router = APIRouter(prefix="/signals", tags=["signals"])


@router.get("")
def signals_index(
    days: int = Query(default=7, ge=1, le=3650),
    monitor: str | None = Query(default=None, max_length=64),
    signal_type: str | None = Query(default=None, alias="type", max_length=64),
    min_level: int = Query(default=0, alias="level", ge=0, le=3),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_db_session),
) -> dict:
    filters = {
        "monitor": monitor,
        "signal_type": signal_type,
        "days": days,
        "min_level": min_level,
    }
    return {
        "items": list_signals(session, limit=limit, offset=offset, **filters),
        "total": count_signals(session, **filters),
        "limit": limit,
        "offset": offset,
    }


@router.get("/{signal_id}")
def signal_detail(
    signal_id: int,
    session: Session = Depends(get_db_session),
) -> dict:
    signal = get_signal_detail(session, signal_id)
    if signal is None:
        raise HTTPException(status_code=404, detail="Signal not found")
    return signal


@router.post("/{signal_id}/actions")
def create_signal_action(
    signal_id: int,
    payload: SignalActionCreate,
    response: Response,
    session: Session = Depends(get_db_session),
    _access: None = Depends(require_write_access),
) -> dict:
    if SignalEventRepository(session).by_id(signal_id) is None:
        raise HTTPException(status_code=404, detail="Signal not found")
    if payload.paper_trade_id is not None:
        trade = PaperTradeRepository(session).by_id(payload.paper_trade_id)
        if trade is None:
            raise HTTPException(status_code=404, detail="Paper trade not found")

    row, created = TradeSignalLinkRepository(session).create_idempotent(
        signal_id,
        payload.decision,
        paper_trade_id=payload.paper_trade_id,
        reason=payload.reason,
    )
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return {**trade_signal_link_to_dict(row), "created": created}


@router.post("/{signal_id}/notes")
def create_signal_note(
    signal_id: int,
    payload: SignalNoteCreate,
    response: Response,
    session: Session = Depends(get_db_session),
    _access: None = Depends(require_write_access),
) -> dict:
    if SignalEventRepository(session).by_id(signal_id) is None:
        raise HTTPException(status_code=404, detail="Signal not found")
    row, created = SignalNoteRepository(session).create_idempotent(signal_id, payload.body)
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return {**signal_note_to_dict(row), "created": created}
