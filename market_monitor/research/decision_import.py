"""Import AI decision JSONL records into structured SQL signals."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Iterable

from sqlalchemy import select

from ..data.models import SignalEvent
from ..data.repositories import SignalEventRepository


_DIRECTION_MAP = {
    "bullish": (1, "decision_bullish"),
    "bearish": (-1, "decision_bearish"),
    "neutral": (0, "decision_neutral"),
}


def read_decision_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def import_decisions(session, records: Iterable[dict]) -> list:
    """Persist decision tracker records as SignalEvent rows."""

    repo = SignalEventRepository(session)
    existing = _existing_decision_ids(session)
    created = []
    for record in records:
        decision_id = record.get("id")
        if decision_id and decision_id in existing:
            continue
        direction_text = str(record.get("direction") or "neutral")
        direction, signal_type = _DIRECTION_MAP.get(direction_text, _DIRECTION_MAP["neutral"])
        date_text = record.get("date") or str(record.get("id", ""))[:10]
        ts = _parse_ts(record.get("extracted_at"), date_text)
        metrics = {
            "title": record.get("claim") or "AI decision",
            "summary": record.get("claim") or "",
            "direction": direction,
            "decision_id": decision_id,
            "direction_text": direction_text,
            "subject": record.get("subject"),
            "timeframe": record.get("timeframe"),
            "source_type": record.get("source_type"),
            "confidence": record.get("confidence"),
            "verdict": record.get("verdict"),
            "verdict_note": record.get("verdict_note"),
            "user_action": record.get("user_action"),
            "user_note": record.get("user_note"),
            "source": "decision_tracker_jsonl",
        }
        created.append(
            repo.create(
                monitor="decision",
                signal_type=signal_type,
                symbol=None,
                level=1,
                metrics=metrics,
                ts=ts,
            )
        )
        if decision_id:
            existing.add(decision_id)
    return created


def _parse_ts(value, date_text: str | None) -> datetime:
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            pass
    if date_text:
        try:
            return datetime.fromisoformat(f"{date_text}T00:00:00")
        except ValueError:
            pass
    return datetime.utcnow()


def _existing_decision_ids(session) -> set[str]:
    q = select(SignalEvent).where(SignalEvent.monitor == "decision")
    ids = set()
    for row in session.execute(q).scalars().all():
        metrics = row.metrics_json or {}
        if isinstance(metrics, dict) and metrics.get("decision_id"):
            ids.add(str(metrics["decision_id"]))
    return ids
