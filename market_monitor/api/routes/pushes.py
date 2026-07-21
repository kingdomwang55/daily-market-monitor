"""Read-only push log endpoints."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ...data.repositories import PushLogRepository
from ...data.serializers import push_log_to_dict
from ..deps import get_db_session


router = APIRouter(prefix="/pushes", tags=["pushes"])


@router.get("")
def pushes_index(
    days: int = Query(default=7, ge=1, le=3650),
    monitor: Optional[str] = Query(default=None, max_length=64),
    min_level: int = Query(default=0, alias="level", ge=0, le=3),
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_db_session),
) -> dict:
    repository = PushLogRepository(session)
    items = repository.recent(
        monitor=monitor,
        days=days,
        min_level=min_level,
        limit=limit,
        offset=offset,
    )
    return {
        "items": [push_log_to_dict(row) for row in items],
        "total": repository.count(
            monitor=monitor,
            days=days,
            min_level=min_level,
        ),
        "limit": limit,
        "offset": offset,
    }


@router.get("/{push_id}")
def push_detail(
    push_id: int,
    session: Session = Depends(get_db_session),
) -> dict:
    row = PushLogRepository(session).by_id(push_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Push log not found")
    return push_log_to_dict(row)
