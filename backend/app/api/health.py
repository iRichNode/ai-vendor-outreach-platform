"""Health checks used by Docker healthcheck + reverse proxy."""
from __future__ import annotations

import json
from typing import Annotated

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.auth import JsonRequest
from app.database import get_db

router = APIRouter(tags=["health"])


async def _db_ping(db: AsyncSession) -> str | None:
    try:
        await db.execute(text("SELECT 1"))
        return None
    except Exception as exc:  # noqa: BLE001
        return f"database: {exc!r}"


async def _redis_ping() -> str | None:
    settings = get_settings()
    if not settings.REDIS_URL or settings.ENVIRONMENT == "test":
        return None
    try:
        client = aioredis.from_url(settings.REDIS_URL, socket_connect_timeout=1)
        await client.ping()
        await client.aclose()
        return None
    except Exception as exc:  # noqa: BLE001
        return f"redis: {exc!r}"


@router.get("/health", summary="Liveness check")
async def health() -> dict:
    return {
        "status": "ok",
        "service": "backend",
        "demo_mode": get_settings().DEMO_MODE,
    }


@router.get("/health/full", summary="Dependency health check")
async def health_full(db: Annotated[AsyncSession, Depends(get_db)]) -> Response:
    problems: list[str] = []
    db_err = await _db_ping(db)
    redis_err = await _redis_ping()
    if db_err:
        problems.append(db_err)
    if redis_err:
        problems.append(redis_err)
    degraded = bool(problems)
    return Response(
        content=json.dumps(
            {
                "status": "degraded" if degraded else "ok",
                "database": "ok" if not db_err else "error",
                "redis": "ok" if not redis_err else "error",
                "problems": problems,
            }
        ),
        media_type="application/json",
        status_code=503 if degraded else 200,
    )