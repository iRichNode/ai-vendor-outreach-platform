"""Small rate limiter.

Uses a Redis sliding window when REDIS_URL is configured, otherwise an in-process
fallback. Intended for auth endpoints (login, setup, OAuth callbacks, notification
test endpoints). Configured via AUTH_RATE_LIMIT like "10/minute".
"""
from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Literal

import redis.asyncio as aioredis
from fastapi import HTTPException, Request, status

from app.config import get_settings

_InMemory: dict[str, deque[float]] = defaultdict(deque)
_redis_client: aioredis.Redis | None = None


def _get_redis() -> aioredis.Redis | None:
    global _redis_client
    settings = get_settings()
    if not settings.REDIS_URL or settings.ENVIRONMENT == "test":
        return None
    if _redis_client is None:
        try:
            _redis_client = aioredis.from_url(settings.REDIS_URL, socket_connect_timeout=1)
        except Exception:  # noqa: BLE001
            _redis_client = None
    return _redis_client


def _parse_spec(spec: str) -> tuple[int, int]:
    """'10/minute' -> (10, 60); '100/hour' -> (100, 3600)."""
    try:
        amount, unit = spec.split("/")
        seconds = {"second": 1, "minute": 60, "hour": 3600, "day": 86400}[unit]
        return int(amount), seconds
    except (ValueError, KeyError):
        return 10, 60


async def redis_check(key: str, limit: int, window: int) -> bool:
    client = _get_redis()
    if client is None:
        return False
    try:
        pipe = client.pipeline()
        now = int(time.time())
        prefix = f"rl:{now // window}:{key}"
        pipe.incr(prefix)
        pipe.expire(prefix, window * 2)
        count = await pipe.execute()
        return int(count[0]) > limit
    except Exception:  # noqa: BLE001 - fail open to in-memory on Redis errors
        return False


def _memory_check(key: str, limit: int, window: int) -> bool:
    now = time.monotonic()
    bucket = _InMemory[key]
    while bucket and now - bucket[0] > window:
        bucket.popleft()
    if len(bucket) >= limit:
        return True
    bucket.append(now)
    return False


def rate_limit(spec: str):
    """FastAPI dependency factory: rate_limit(\"10/minute\")."""
    limit, window = _parse_spec(spec)

    async def dependency(request: Request) -> None:
        client_ip = request.client.host if request.client else "unknown"
        key = f"{client_ip}:{request.url.path}"
        exceeded = await redis_check(key, limit, window) or _memory_check(key, limit, window)
        if exceeded:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests, slow down",
                headers={"Retry-After": str(window)},
            )

    return dependency