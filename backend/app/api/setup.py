"""First-run setup wizard.

Creates the initial admin account. Only works while no users exist (or when an
explicit setup token is provided). Passwords come from the operator, never from
source code; INITIAL_ADMIN_* env vars are also supported for scripted deploys.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.auth import JsonRequest
from app.core.ratelimit import rate_limit
from app.core.security import create_session_token, hash_password
from app.database import get_db
from app.models.user import User
from app.schemas.auth import SetupRequest, UserOut
from app.services import settings_service

router = APIRouter(prefix="/setup", tags=["setup"])


async def count_users(db: AsyncSession) -> int:
    return (await db.execute(select(func.count(User.id)))).scalar_one()


@router.get("/status")
async def setup_status(db: AsyncSession = Depends(get_db)) -> dict:
    return {
        "setup_required": (await count_users(db)) == 0,
        "demo_mode": get_settings().DEMO_MODE,
    }


@router.post(
    "/complete",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit("10/minute"))],
)
async def complete_setup(
    body: SetupRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> User:
    if (await count_users(db)) > 0:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Setup already completed")
    existing = (await db.execute(select(User).where(User.username == body.username))).scalars().first()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already taken")
    user = User(
        username=body.username,
        email=body.email,
        password_hash=hash_password(body.password),
        is_active=True,
        is_superuser=True,
    )
    db.add(user)
    await db.flush()
    await settings_service.ensure_default_settings(db)
    await db.commit()

    settings = get_settings()
    response.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=create_session_token(user.id, user.username),
        max_age=settings.SESSION_EXPIRE_MINUTES * 60,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        path="/",
    )
    return user


async def setup_from_env_if_needed(db: AsyncSession) -> User | None:
    """Create the initial admin from env vars (used by the CLI helper)."""
    settings = get_settings()
    if (await count_users(db)) > 0 or not settings.INITIAL_ADMIN_USERNAME or not settings.INITIAL_ADMIN_PASSWORD:
        return None
    username = settings.INITIAL_ADMIN_USERNAME
    if (await db.execute(select(User).where(User.username == username))).scalars().first():
        return None
    user = User(
        username=username,
        email=settings.INITIAL_ADMIN_EMAIL or None,
        password_hash=hash_password(settings.INITIAL_ADMIN_PASSWORD),
        is_active=True,
        is_superuser=True,
    )
    db.add(user)
    await db.flush()
    await settings_service.ensure_default_settings(db)
    await db.commit()
    return user