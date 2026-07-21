"""Validated request contracts for local Web mutations."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


class SignalActionCreate(BaseModel):
    decision: Literal["act", "skip", "watch", "noise"]
    reason: Optional[str] = Field(default=None, max_length=2000)
    paper_trade_id: Optional[int] = Field(default=None, gt=0)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: Optional[str]) -> Optional[str]:
        return value.strip() or None if value is not None else None


class SignalNoteCreate(BaseModel):
    body: str = Field(min_length=1, max_length=4000)

    @field_validator("body")
    @classmethod
    def normalize_body(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Note cannot be blank")
        return normalized


class TradeCreate(BaseModel):
    request_id: str = Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    symbol: str = Field(min_length=1, max_length=64, pattern=r"^\S+$")
    name: Optional[str] = Field(default=None, max_length=128)
    action: Literal["long", "short"] = "long"
    strategy: Optional[str] = Field(default=None, max_length=64)
    tag: Optional[str] = Field(default=None, max_length=64)
    entry_price: float = Field(gt=0)
    qty: float = Field(gt=0)
    entry_reason: Optional[str] = Field(default=None, max_length=4000)
    stop_loss: Optional[float] = Field(default=None, gt=0)
    take_profit: Optional[float] = Field(default=None, gt=0)
    signal_event_id: Optional[int] = Field(default=None, gt=0)
    notes: Optional[str] = Field(default=None, max_length=4000)

    @field_validator("symbol", "name", "strategy", "tag", "entry_reason", "notes")
    @classmethod
    def strip_strings(cls, value: Optional[str]) -> Optional[str]:
        return value.strip() or None if value is not None else None


class TradeClose(BaseModel):
    close_price: float = Field(gt=0)
    close_reason: Optional[str] = Field(default=None, max_length=4000)

    @field_validator("close_reason")
    @classmethod
    def normalize_reason(cls, value: Optional[str]) -> Optional[str]:
        return value.strip() or None if value is not None else None


class ReviewGenerate(BaseModel):
    period_type: Literal["week", "month"]
    period_key: Optional[str] = Field(default=None, max_length=16)
