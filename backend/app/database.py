"""Async SQLAlchemy engine, session factory and base class."""
from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings
from app.models.base import Base  # shared declarative base used by every model


def create_engine_and_session(database_url: str | None = None):
    settings = get_settings()
    url = database_url or settings.DATABASE_URL
    engine = create_async_engine(url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    return engine, session_factory


_engine, _session_factory = create_engine_and_session()


def get_engine():
    return _engine


def get_session_factory():
    return _session_factory


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding a database session."""
    factory = _session_factory
    async with factory() as session:
        yield session


async def init_db() -> None:
    """Create all tables (used by tests and demo mode; production uses Alembic)."""
    from app.models import all_models  # noqa: F401  ensure models are registered

    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def dispose_db() -> None:
    await _engine.dispose()