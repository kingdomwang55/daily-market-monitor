"""Optional write-token protection for future LAN deployments."""

from __future__ import annotations

import hmac
import os
from typing import Optional

from fastapi import Header, HTTPException


def require_write_access(
    authorization: Optional[str] = Header(default=None),
    x_market_token: Optional[str] = Header(default=None),
) -> None:
    expected = os.getenv("MARKET_WEB_TOKEN")
    if not expected:
        return
    bearer = None
    if authorization and authorization.startswith("Bearer "):
        bearer = authorization.removeprefix("Bearer ").strip()
    supplied = x_market_token or bearer
    if supplied is None or not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="Valid write token required")
