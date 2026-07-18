"""Human notes attached to immutable signal events."""

from __future__ import annotations

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from ..models import SignalNote


class SignalNoteRepository:
    def __init__(self, session: Session):
        self.s = session

    def create_idempotent(self, signal_event_id: int, body: str) -> tuple[SignalNote, bool]:
        normalized = body.strip()
        existing = self.s.execute(
            select(SignalNote)
            .where(
                SignalNote.signal_event_id == signal_event_id,
                SignalNote.body == normalized,
            )
            .order_by(desc(SignalNote.created_at))
            .limit(1)
        ).scalars().first()
        if existing is not None:
            return existing, False

        row = SignalNote(signal_event_id=signal_event_id, body=normalized)
        self.s.add(row)
        self.s.flush()
        return row, True

    def by_signal(self, signal_event_id: int) -> list[SignalNote]:
        query = (
            select(SignalNote)
            .where(SignalNote.signal_event_id == signal_event_id)
            .order_by(desc(SignalNote.created_at), desc(SignalNote.id))
        )
        return list(self.s.execute(query).scalars().all())
