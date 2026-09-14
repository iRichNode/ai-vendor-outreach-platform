"""Authentication endpoints (login, logout, current user)."""
from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.auth import CurrentUser, JsonRequest
from app.core.ratelimit import rate_limit
from app.core.security import create_session_token, verify_password
from app.database import get_db
from app.models.user import User
from app.schemas.auth import AuthStatus, LoginRequest, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_session_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=token,
        max_age=settings.SESSION_EXPIRE_MINUTES * 60,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        path="/",
    )


def _clear_session_cookie(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(key=settings.SESSION_COOKIE_NAME, path="/")


@router.post("/login", response_model=UserOut, dependencies=[Depends(rate_limit("10/minute"))])
async def login(
    body: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> User:
    user = (await db.execute(select(User).where(User.username == body.username))).scalars().first()
    if user is None or not verify_password(body.password, user.password_hash) or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")
    user.last_login_at = datetime.now(UTC)
    await db.commit()
    _set_session_cookie(response, create_session_token(user.id, user.username))
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def logout(response: Response, _: CurrentUser, _json: JsonRequest) -> Response:
    _clear_session_cookie(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/me", response_model=AuthStatus)
async def me(request: Request, db: AsyncSession = Depends(get_db)) -> AuthStatus:
    from app.core.auth import get_current_user as _get_current_user

    try:
        user = await _get_current_user(request, db)
    except HTTPException:
        return AuthStatus(authenticated=False, user=None)
    return AuthStatus(authenticated=True, user=UserOut.model_validate(user))