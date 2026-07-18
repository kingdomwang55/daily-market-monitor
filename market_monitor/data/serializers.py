"""Stable JSON serializers shared by CLI and Web API read paths."""

from __future__ import annotations

from typing import Any


def iso_datetime(value) -> str | None:
    if value is None:
        return None
    return value.isoformat() + ("Z" if getattr(value, "tzinfo", None) is None else "")


def push_log_to_dict(row, *, include_body: bool = True) -> dict[str, Any]:
    signals = [
        {
            "id": signal.id,
            "signal_type": signal.signal_type,
            "symbol": signal.symbol,
            "level": signal.level,
        }
        for signal in getattr(row, "signals", [])
    ]
    payload = {
        "id": row.id,
        "ts": iso_datetime(row.ts),
        "trade_date": row.trade_date.isoformat(),
        "monitor": row.monitor,
        "scenario": row.scenario,
        "max_level": row.max_level,
        "title": row.title,
        "sent_ok": row.sent_ok,
        "error": row.error,
        "signal_ids": [signal["id"] for signal in signals],
        "signal_types": [signal["signal_type"] for signal in signals],
        "signals": signals,
    }
    if include_body:
        payload["message"] = row.message
        payload["context"] = row.context_json or {}
    return payload


def paper_trade_to_dict(row) -> dict[str, Any]:
    return {
        "id": row.id,
        "request_id": row.request_id,
        "symbol": row.symbol,
        "name": row.name,
        "action": row.action,
        "strategy": row.strategy,
        "tag": row.tag,
        "status": row.status,
        "entry_at": iso_datetime(row.entry_at),
        "entry_price": row.entry_price,
        "qty": row.qty,
        "entry_reason": row.entry_reason,
        "close_at": iso_datetime(row.close_at),
        "close_price": row.close_price,
        "close_reason": row.close_reason,
        "stop_loss": row.stop_loss,
        "take_profit": row.take_profit,
        "pnl": row.pnl,
        "pnl_pct": row.pnl_pct,
        "hold_days": row.hold_days,
        "signal_event_id": row.signal_event_id,
        "notes": row.notes,
    }


def trade_signal_link_to_dict(row) -> dict[str, Any]:
    return {
        "id": row.id,
        "signal_event_id": row.signal_event_id,
        "paper_trade_id": row.paper_trade_id,
        "decision": row.decision,
        "reason": row.reason,
        "created_at": iso_datetime(row.created_at),
    }


def signal_note_to_dict(row) -> dict[str, Any]:
    return {
        "id": row.id,
        "signal_event_id": row.signal_event_id,
        "body": row.body,
        "created_at": iso_datetime(row.created_at),
        "updated_at": iso_datetime(row.updated_at),
    }


def trade_review_to_dict(row) -> dict[str, Any]:
    return {
        "period_type": row.period_type,
        "period_key": row.period_key,
        "trade_count": row.trade_count,
        "win_count": row.win_count,
        "loss_count": row.loss_count,
        "win_rate": row.win_rate,
        "total_pnl": row.total_pnl,
        "avg_win": row.avg_win,
        "avg_loss": row.avg_loss,
        "max_drawdown": row.max_drawdown,
        "best_trade_id": row.best_trade_id,
        "worst_trade_id": row.worst_trade_id,
        "notes": row.notes,
        "generated_at": iso_datetime(row.generated_at),
    }
