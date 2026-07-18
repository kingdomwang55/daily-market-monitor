"""Validated paper trade journal endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from ...data.repositories import (
    PaperTradeRepository,
    SignalEventRepository,
    TradeSignalLinkRepository,
)
from ...data.serializers import paper_trade_to_dict
from ..deps import get_db_session
from ..schemas import TradeClose, TradeCreate
from ..security import require_write_access


router = APIRouter(prefix="/trades", tags=["trades"])


@router.get("")
def trades_index(
    status: str | None = Query(default=None, pattern="^(open|closed)$"),
    symbol: str | None = Query(default=None, max_length=64),
    strategy: str | None = Query(default=None, max_length=64),
    days: int | None = Query(default=None, ge=1, le=3650),
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_db_session),
) -> dict:
    repository = PaperTradeRepository(session)
    filters = {"status": status, "symbol": symbol, "strategy": strategy, "days": days}
    rows = repository.recent(limit=limit, offset=offset, **filters)
    return {
        "items": [paper_trade_to_dict(row) for row in rows],
        "total": repository.count(**filters),
        "limit": limit,
        "offset": offset,
    }


@router.post("")
def create_trade(
    payload: TradeCreate,
    response: Response,
    session: Session = Depends(get_db_session),
    _access: None = Depends(require_write_access),
) -> dict:
    if payload.signal_event_id is not None:
        signal = SignalEventRepository(session).by_id(payload.signal_event_id)
        if signal is None:
            raise HTTPException(status_code=404, detail="Signal not found")

    repository = PaperTradeRepository(session)
    existing = repository.by_request_id(payload.request_id)
    values = payload.model_dump(exclude={"request_id"})
    if existing is not None:
        same_request = all(getattr(existing, key) == value for key, value in values.items())
        if not same_request:
            raise HTTPException(status_code=409, detail="Request ID already used")
        row, created = existing, False
    else:
        row, created = repository.open_trade_idempotent(payload.request_id, **values)

    if payload.signal_event_id is not None:
        TradeSignalLinkRepository(session).create_idempotent(
            payload.signal_event_id,
            "act",
            paper_trade_id=row.id,
            reason=payload.entry_reason,
        )
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return {**paper_trade_to_dict(row), "created": created}


@router.patch("/{trade_id}/close")
def close_trade(
    trade_id: int,
    payload: TradeClose,
    session: Session = Depends(get_db_session),
    _access: None = Depends(require_write_access),
) -> dict:
    repository = PaperTradeRepository(session)
    existing = repository.by_id(trade_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Trade not found")
    if existing.status == "closed":
        raise HTTPException(status_code=409, detail="Trade is already closed")
    row = repository.close_trade(
        trade_id,
        payload.close_price,
        close_reason=payload.close_reason,
    )
    return paper_trade_to_dict(row)


@router.get("/{trade_id}")
def trade_detail(
    trade_id: int,
    session: Session = Depends(get_db_session),
) -> dict:
    row = PaperTradeRepository(session).by_id(trade_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Trade not found")
    return paper_trade_to_dict(row)
