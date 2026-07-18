FROM node:22-alpine AS frontend-builder

WORKDIR /build/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build


FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    MARKET_WEB_HOST=0.0.0.0 \
    MARKET_WEB_PORT=8000 \
    MARKET_WEB_DIST=/app/frontend/dist

WORKDIR /app

COPY pyproject.toml README.md ./
RUN mkdir -p market_monitor \
    && touch market_monitor/__init__.py \
    && pip install --no-cache-dir . \
    && rm -rf market_monitor

COPY market_monitor/ ./market_monitor/
RUN pip install --no-cache-dir --no-deps --force-reinstall .

COPY alembic.ini ./
COPY alembic/ ./alembic/
COPY config/ ./config/
COPY scripts/docker_entrypoint.sh scripts/gen_launchd.py ./scripts/
COPY --from=frontend-builder /build/frontend/dist ./frontend/dist

RUN chmod +x ./scripts/docker_entrypoint.sh && mkdir -p /app/data

EXPOSE 8000
VOLUME ["/app/data"]

ENTRYPOINT ["/app/scripts/docker_entrypoint.sh"]
CMD ["market-monitor-web"]
