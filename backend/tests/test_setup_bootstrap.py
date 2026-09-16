"""Tests for the INITIAL_ADMIN_* first-boot bootstrap (setup_from_env_if_needed).

The function must:
  - create an active superuser (with default settings rows) when the users
    table is empty and INITIAL_ADMIN_USERNAME/PASSWORD are configured;
  - be idempotent (no-op on second call / when any user already exists);
  - no-op when the env vars are missing.

These tests run against the real PostgreSQL instance (see conftest.py) and
clean the users table after each test so they stay order-independent.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

import pytest
import pytest_asyncio
from sqlalchemy import delete, func, select

from app.api.setup import setup_from_env_if_needed
from app.config import get_settings
from app.core.security import hash_password, verify_password
from app.database import get_session_factory
from app.models.user import User


@asynccontextmanager
async def _session():
    """Open a short-lived AsyncSession from the app's session factory."""
    factory = get_session_factory()
    async with factory() as db:
        yield db


async def _user_count() -> int:
    async with _session() as db:
        return (await db.execute(select(func.count()).select_from(User))).scalar_one()


async def _usernames() -> set[str]:
    async with _session() as db:
        return set((await db.execute(select(User.username))).scalars().all())


@pytest.fixture(autouse=True)
def _bootstrap_env(monkeypatch):
    """Point INITIAL_ADMIN_* at deterministic values on the cached settings."""
    settings = get_settings()
    monkeypatch.setattr(settings, "INITIAL_ADMIN_USERNAME", "bootstrap_admin", raising=False)
    monkeypatch.setattr(settings, "INITIAL_ADMIN_PASSWORD", "bootstrap-secret-123", raising=False)
    monkeypatch.setattr(settings, "INITIAL_ADMIN_EMAIL", "bootstrap@example.com", raising=False)


@pytest_asyncio.fixture(autouse=True)
async def _clean_users():
    # Clean both sides: earlier integration modules (test_api_flow) leave the
    # first admin behind, and these tests must see a known users table.
    async with _session() as db:
        await db.execute(delete(User))
        await db.commit()
    yield
    async with _session() as db:
        await db.execute(delete(User))
        await db.commit()


async def test_creates_active_superuser_when_table_empty():
    async with _session() as db:
        created = await setup_from_env_if_needed(db)
        assert created is not None
        assert created.username == "bootstrap_admin"
        assert created.is_active is True
        assert created.is_superuser is True
        assert verify_password("bootstrap-secret-123", created.password_hash)
    assert await _user_count() == 1


async def test_second_call_is_noop():
    async with _session() as db:
        assert await setup_from_env_if_needed(db) is not None
        assert await setup_from_env_if_needed(db) is None
    assert await _user_count() == 1


async def test_noop_when_any_user_already_exists():
    async with _session() as db:
        db.add(
            User(
                username="someone_else",
                email="someone@example.com",
                password_hash=hash_password("not-the-bootstrap-secret"),
                is_active=True,
                is_superuser=False,
            )
        )
        await db.commit()

        assert await setup_from_env_if_needed(db) is None

    assert await _user_count() == 1
    assert await _usernames() == {"someone_else"}


async def test_noop_when_env_vars_missing(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "INITIAL_ADMIN_USERNAME", "", raising=False)
    monkeypatch.setattr(settings, "INITIAL_ADMIN_PASSWORD", "", raising=False)
    async with _session() as db:
        assert await setup_from_env_if_needed(db) is None
    assert await _user_count() == 0
