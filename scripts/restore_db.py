#!/usr/bin/env python3
"""Restore a checked SQLite backup while preserving the current database."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from market_monitor.ops.sqlite_backup import restore_database  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from", dest="backup", type=Path, required=True, help="Backup .db file")
    parser.add_argument("--target", type=Path, help="SQLite file; defaults to MARKET_DB_URL")
    parser.add_argument("--yes", action="store_true", help="Confirm that the application is stopped")
    args = parser.parse_args()
    if not args.yes:
        parser.error("stop the application, then pass --yes to confirm the restore")
    target, safety_backup = restore_database(args.backup, args.target)
    print(f"restored: {target}")
    if safety_backup:
        print(f"previous database: {safety_backup}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
