"""Sanitized local system and operability status."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ...core.doctor import run_checks
from ...data.database import db_info
from ...data.repositories import SystemRepository
from ...data.serializers import iso_datetime
from ..deps import get_db_session


router = APIRouter(prefix="/system", tags=["system"])


@router.get("/status")
def system_status(session: Session = Depends(get_db_session)) -> dict:
    repository = SystemRepository(session)
    monitor_rows = repository.monitor_statuses()
    checks = run_checks(ci=True)
    info = db_info()
    return {
        "database": {
            "engine": "sqlite" if info["is_sqlite"] else "external",
            "path": info["path"] if info["is_sqlite"] else None,
        },
        "monitors": [
            {**row, "last_push_at": iso_datetime(row["last_push_at"])}
            for row in monitor_rows
        ],
        "tables": repository.table_counts(),
        "checks": [
            {"name": check.name, "ok": check.ok, "message": check.message}
            for check in checks
        ],
        "healthy": all(check.ok for check in checks),
    }
