"""FastAPI application entrypoint.

Run locally:
    uvicorn app.main:app --reload

Run with Docker:
    gunicorn app.main:app -k uvicorn.workers.UvicornWorker -w 2 -b 0.0.0.0:8000
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from typing import Annotated

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import api_router
from app.api.health import health as _health
from app.api.health import health_full as _health_full
from app.database import get_db
from app.config import get_settings
from app.database import init_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("app.main")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = get_settings()
    if settings.ENVIRONMENT in ("development", "test") or settings.DEMO_MODE:
        logger.warning("Creating tables via create_all (dev/demo mode). Production must use Alembic.")
        await init_db()
    logger.info("startup complete environment=%s demo_mode=%s", settings.ENVIRONMENT, settings.DEMO_MODE)
    yield


app = FastAPI(
    title="AI Vendor Outreach Platform API",
    version="1.0.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.API_PREFIX)


@app.get("/health", include_in_schema=False, summary="Liveness (reverse proxy)")
async def root_health() -> dict:
    """Root-level liveness probe used by nginx and load balancers."""
    return await _health()


@app.get("/ready", include_in_schema=False, summary="Readiness (dependencies)")
async def root_ready(db: Annotated[AsyncSession, Depends(get_db)]) -> dict:
    """Root-level readiness probe verifying database and Redis connectivity."""
    return await _health_full(db=db)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Last-resort handler so the dashboard never sees raw tracebacks."""
    logger.exception("unhandled_error path=%s", request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "path": request.url.path},
    )


@app.get("/", include_in_schema=False)
async def root() -> dict:
    return {
        "service": "ai-vendor-outreach-platform",
        "docs": "/api/docs",
        "health": "/api/health",
    }