"""Shared SQLite path resolution for direct sqlite cache modules."""
from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import unquote, urlparse


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "market.db"


def sqlite_path_from_url(db_url: str | None) -> Path | None:
    """Return a filesystem path for sqlite URLs, or None for non-sqlite URLs."""
    if not db_url or not db_url.startswith("sqlite"):
        return None
    parsed = urlparse(db_url)
    if parsed.path in ("", "/:memory:") or parsed.path.endswith(":memory:"):
        return None
    path = unquote(parsed.path)
    if parsed.netloc and parsed.netloc != "":
        path = f"//{parsed.netloc}{path}"
    if path.startswith("//") and not db_url.startswith("sqlite://///"):
        path = path[1:]
    return Path(path)


def sqlite_db_path() -> Path:
    """Resolve the active SQLite path from MARKET_DB_URL, falling back to data/market.db."""
    return sqlite_path_from_url(os.getenv("MARKET_DB_URL")) or DEFAULT_DB_PATH


def ensure_sqlite_parent(path: Path) -> None:
    """Create the parent directory for a file-backed SQLite database."""
    path.parent.mkdir(parents=True, exist_ok=True)
