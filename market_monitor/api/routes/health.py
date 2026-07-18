"""Health endpoints for local and container probes."""

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ...data.database import db_info
from ..deps import get_db_session


router = APIRouter(tags=["system"])


@router.get("/health")
def health(response: Response, session: Session = Depends(get_db_session)) -> dict:
    try:
        session.execute(text("SELECT 1"))
        database_status = "ok"
    except SQLAlchemyError:
        session.rollback()
        database_status = "error"
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    info = db_info()
    return {
        "status": "ok" if database_status == "ok" else "degraded",
        "database": {
            "status": database_status,
            "engine": "sqlite" if info["is_sqlite"] else "external",
        },
    }
