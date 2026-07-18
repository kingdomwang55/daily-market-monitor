#!/usr/bin/env sh
set -eu

python -m alembic -c /app/alembic.ini upgrade head
python -m market_monitor.cli db init

exec "$@"
