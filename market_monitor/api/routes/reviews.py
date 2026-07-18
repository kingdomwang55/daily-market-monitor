"""Weekly and monthly review endpoints."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from ...data.repositories import TradeReviewRepository
from ...data.serializers import trade_review_to_dict
from ...research.reviews import review_detail, review_markdown
from ..deps import get_db_session
from ..schemas import ReviewGenerate
from ..security import require_write_access


router = APIRouter(prefix="/reviews", tags=["reviews"])


@router.get("")
def reviews_index(
    period_type: str = Query(default="week", pattern="^(week|month)$"),
    limit: int = Query(default=12, ge=1, le=100),
    session: Session = Depends(get_db_session),
) -> dict:
    rows = TradeReviewRepository(session).recent(period_type=period_type, limit=limit)
    return {"items": [trade_review_to_dict(row) for row in rows]}


@router.post("/generate")
def generate_review(
    payload: ReviewGenerate,
    session: Session = Depends(get_db_session),
    _access: None = Depends(require_write_access),
) -> dict:
    repository = TradeReviewRepository(session)
    period_key = payload.period_key
    if period_key is None:
        period_key = (
            repository.week_key(datetime.utcnow())
            if payload.period_type == "week"
            else repository.month_key(datetime.utcnow())
        )
    row = repository.generate(payload.period_type, period_key)
    if row is None:
        raise HTTPException(status_code=422, detail="Invalid review period key")
    return review_detail(session, row)


@router.get("/{period_type}/{period_key}")
def get_review(
    period_type: str,
    period_key: str,
    session: Session = Depends(get_db_session),
) -> dict:
    if period_type not in {"week", "month"}:
        raise HTTPException(status_code=422, detail="Invalid review period type")
    row = TradeReviewRepository(session).by_key(period_type, period_key)
    if row is None:
        raise HTTPException(status_code=404, detail="Review not found")
    return review_detail(session, row)


@router.get("/{period_type}/{period_key}/markdown", response_class=PlainTextResponse)
def export_review_markdown(
    period_type: str,
    period_key: str,
    session: Session = Depends(get_db_session),
) -> PlainTextResponse:
    row = TradeReviewRepository(session).by_key(period_type, period_key)
    if row is None:
        raise HTTPException(status_code=404, detail="Review not found")
    body = review_markdown(review_detail(session, row))
    filename = f"review-{period_type}-{period_key}.md"
    return PlainTextResponse(
        body,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
