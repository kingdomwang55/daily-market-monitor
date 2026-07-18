"""Read-side queries for monitor and signal metadata registries."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import MonitorRegistry


class RegistryRepository:
    def __init__(self, session: Session):
        self.s = session

    def monitors(self, *, enabled: bool | None = None):
        query = select(MonitorRegistry)
        if enabled is not None:
            query = query.where(MonitorRegistry.enabled == enabled)
        query = query.order_by(MonitorRegistry.category, MonitorRegistry.name)
        return self.s.execute(query).scalars().all()
