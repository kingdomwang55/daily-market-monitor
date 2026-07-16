#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-python3}"
tmp_launchd="$(mktemp -d)"
tmp_db="$(mktemp -d)"
trap 'rm -rf "$tmp_launchd" "$tmp_db"' EXIT

"$PYTHON_BIN" -m unittest discover -s tests -v
"$PYTHON_BIN" tests/test_data_source.py
"$PYTHON_BIN" -m compileall -q market_monitor scripts tests
"$PYTHON_BIN" -m market_monitor.cli list
MARKET_MONITOR_LAUNCHD_DIR="$tmp_launchd" "$PYTHON_BIN" scripts/gen_launchd.py
MARKET_MONITOR_LAUNCHD_DIR="$tmp_launchd" "$PYTHON_BIN" -m market_monitor.cli doctor --ci
MARKET_DB_URL="sqlite:///$tmp_db/market.db" "$PYTHON_BIN" -m alembic -c alembic.ini upgrade head
