"""Read-only aggregate endpoints."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ...data.repositories import StatsRepository
from ..deps import get_db_session


router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("/summary")
def stats_summary(
    days: int = Query(default=7, ge=1, le=3650),
    session: Session = Depends(get_db_session),
) -> dict:
    return StatsRepository(session).web_summary(days=days)
