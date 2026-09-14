"""Docker healthcheck for worker/scheduler services.

Pings PostgreSQL (via SQLAlchemy) and Redis and exits non-zero if either is
unavailable so container healthchecks can react. No long-running state.
"""
from __future__ import annotations

import asyncio
import sys

import redis.asyncio as aioredis

from app.config import get_settings
from app.database import create_engine_and_session


async def _check() -> tuple[bool, list[str]]:
    problems: list[str] = []
    settings = get_settings()
    try:
        _, session_factory = create_engine_and_session()
        async with session_factory() as db:
            from sqlalchemy import text

            await db.execute(text("SELECT 1"))
        if not settings.REDIS_URL:
            problems.append("REDIS_URL is not configured")
        else:
            client = aioredis.from_url(settings.REDIS_URL, socket_connect_timeout=2)
            await client.ping()
            await client.aclose()
    except Exception as exc:  # noqa: BLE001
        problems.append(f"{exc!r}")
    return (not problems), problems


async def main() -> int:
    ok, problems = await _check()
    if ok:
        print("deps ok")
        return 0
    print("deps failing:", "; ".join(problems), file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))