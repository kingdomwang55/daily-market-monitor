#!/usr/bin/env python3
"""Create a consistent backup of the active SQLite database."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from market_monitor.ops.sqlite_backup import backup_database  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, help="SQLite file; defaults to MARKET_DB_URL")
    parser.add_argument("--output", type=Path, help="Destination .db file")
    args = parser.parse_args()
    destination = backup_database(args.source, args.output)
    print(destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
