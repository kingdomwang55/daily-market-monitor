"""FastAPI application serving the JSON API and built Vue frontend."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .routes.health import router as health_router
from .routes.meta import router as meta_router
from .routes.pushes import router as pushes_router
from .routes.reviews import router as reviews_router
from .routes.signals import router as signals_router
from .routes.stats import router as stats_router
from .routes.system import router as system_router
from .routes.trades import router as trades_router


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _frontend_dist() -> Path:
    configured = os.getenv("MARKET_WEB_DIST")
    return Path(configured).expanduser() if configured else PROJECT_ROOT / "frontend" / "dist"


def create_app(frontend_dist: Path | None = None) -> FastAPI:
    app = FastAPI(
        title="Daily Market Monitor API",
        version="0.1.0",
        description="Read-only local research library API.",
    )

    api = APIRouter(prefix="/api")
    api.include_router(health_router)
    api.include_router(meta_router)
    api.include_router(signals_router)
    api.include_router(pushes_router)
    api.include_router(trades_router)
    api.include_router(stats_router)
    api.include_router(reviews_router)
    api.include_router(system_router)
    app.include_router(api)

    dist = frontend_dist or _frontend_dist()
    assets = dist / "assets"
    index = dist / "index.html"

    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="frontend-assets")

    @app.get("/{path:path}", include_in_schema=False)
    def vue_history_fallback(path: str):
        if path == "api" or path.startswith("api/"):
            raise HTTPException(status_code=404, detail="API route not found")
        if index.is_file():
            return FileResponse(index)
        return JSONResponse(
            {
                "name": "daily-market-monitor",
                "status": "frontend_not_built",
                "api": "/api/health",
                "docs": "/docs",
            }
        )

    return app


app = create_app()


def main() -> None:
    import uvicorn

    uvicorn.run(
        "market_monitor.api.server:app",
        host=os.getenv("MARKET_WEB_HOST", "127.0.0.1"),
        port=int(os.getenv("MARKET_WEB_PORT", "8000")),
    )
