"""Read-only metadata endpoints for Web filters."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ...data.repositories import RegistryRepository
from ...signals.query import list_signal_types
from ..deps import get_db_session


router = APIRouter(tags=["metadata"])


@router.get("/monitors")
def monitors_index(
    enabled: Optional[bool] = Query(default=None),
    session: Session = Depends(get_db_session),
) -> dict:
    rows = RegistryRepository(session).monitors(enabled=enabled)
    return {
        "items": [
            {
                "name": row.name,
                "display_name": row.display_name,
                "category": row.category,
                "enabled": row.enabled,
                "description": row.description,
            }
            for row in rows
        ]
    }


@router.get("/signal-types")
def signal_types_index(
    monitor: Optional[str] = Query(default=None, max_length=64),
    session: Session = Depends(get_db_session),
) -> dict:
    return {"items": list_signal_types(session, monitor=monitor)}
