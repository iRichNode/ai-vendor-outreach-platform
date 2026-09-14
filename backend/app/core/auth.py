"""Authentication dependencies for FastAPI routes.

Sessions use a JWT stored in an HttpOnly, SameSite cookie. State-changing requests
must additionally send the `X-Requested-With: XMLHttpRequest` header (CSRF defence in
depth — SameSite=Lax already blocks cross-site cookies).
"""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_session_token
from app.database import get_db
from app.models.user import User


def _unauthorized(detail: str = "Not authenticated") -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)


async def get_current_user(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    from app.config import get_settings

    token = request.cookies.get(get_settings().SESSION_COOKIE_NAME)
    if not token:
        auth = request.headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            token = auth[7:]
    if not token:
        raise _unauthorized()

    payload = decode_session_token(token)
    if not payload:
        raise _unauthorized("Invalid or expired session")

    user = await db.get(User, payload["sub"])
    if user is None or not user.is_active:
        raise _unauthorized()
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def require_json_request(
    x_requested_with: Annotated[str | None, Header()] = None,
) -> None:
    """CSRF-in-depth guard for state-changing JSON API calls."""
    if x_requested_with != "XMLHttpRequest":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Missing X-Requested-With header")


JsonRequest = Annotated[None, Depends(require_json_request)]