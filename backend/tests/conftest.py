"""Shared pytest fixtures.

Integration fixtures use the REAL PostgreSQL and Redis instances (expected at
DATABASE_URL / REDIS_URL) and drive the FastAPI app through httpx ASGITransport.
External providers (Gmail/Telegram/AI/discovery) are all exercised in their
mocked/demo modes, which the app enables when no API keys are configured.
"""
from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("COOKIE_SECURE", "false")

from app.config import get_settings  # noqa: E402
from app.database import dispose_db, init_db  # noqa: E402

@pytest_asyncio.fixture(scope="session", autouse=True)
async def _bootstrap() -> AsyncIterator[None]:
    """Reset DB (create_all) and flush Redis once per session."""
    settings = get_settings()
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy import text

    url = os.environ.get("DATABASE_URL") or str(settings.DATABASE_URL)
    admin_engine = create_async_engine(url, isolation_level="AUTOCOMMIT")
    async with admin_engine.connect() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
    await admin_engine.dispose()

    await init_db()

    import redis.asyncio as aioredis
    r = aioredis.from_url(os.environ.get("REDIS_URL") or str(settings.REDIS_URL))
    await r.flushall()
    await r.aclose()

    yield


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _teardown() -> AsyncIterator[None]:
    yield
    await dispose_db()