"""Integration endpoints: Gmail OAuth connection lifecycle + Telegram status/test.

Tokens are exchanged server-side and stored encrypted at rest; they are never
returned to the browser. The /telegram/test endpoint calls the live Bot API.
"""
from __future__ import annotations

import json
import time
from datetime import UTC, datetime, timedelta
from typing import Annotated
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import HTMLResponse
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.auth import CurrentUser, JsonRequest
from app.core.secrets import decrypt_secret, encrypt_secret
from app.database import get_db
from app.models.email_account import EmailAccount
from app.models.oauth_credential import OAuthCredential
from app.schemas.misc import TelegramTestResult
from app.services import audit
from app.services.gmail_client import SCOPES, build_oauth_url, get_transport
from app.services.serializers import serialize_email_account
from app.services.telegram import TelegramSender

router = APIRouter(prefix="/integrations", tags=["integrations"])

_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
_USERINFO_ENDPOINT = "https://oauth2.googleapis.com/tokeninfo"


@router.get("/gmail/status")
async def gmail_status(db: Annotated[AsyncSession, Depends(get_db)], _user: CurrentUser) -> dict:
    settings = get_settings()
    accounts = (await db.execute(select(EmailAccount))).scalars().all()
    creds = (await db.execute(select(OAuthCredential).where(OAuthCredential.provider == "gmail"))).scalars().all()
    transport = get_transport()
    connected = bool(
        accounts or creds or settings.GMAIL_TOKEN_JSON or settings.GMAIL_TOKEN_FILE
        or settings.GOOGLE_CLIENT_ID
    )
    return {
        "configured": connected,
        "demo_mode": settings.DEMO_MODE,
        "transport": "real" if connected and not settings.GMAIL_TRANSPORT == "fake" else "fake",
        "accounts": [serialize_email_account(a) for a in accounts],
        "oauth_scopes": SCOPES,
    }


@router.get("/gmail/auth-url")
async def gmail_auth_url(
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: CurrentUser,
    redirect_uri: str = Query(default="", max_length=1024),
) -> dict:
    settings = get_settings()
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Google OAuth is not configured (GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET)")
    # Only allow http(s) redirects to avoid open-redirect via OAuth
    if redirect_uri:
        parsed = urlsplit(redirect_uri)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid redirect_uri")
    uri = redirect_uri or settings.GOOGLE_REDIRECT_URI or f"{settings.BASE_URL}/api/integrations/gmail/callback"
    url = build_oauth_url(uri)
    return {"auth_url": url, "redirect_uri": uri}


@router.get("/gmail/callback", response_class=HTMLResponse)
async def gmail_callback(
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: CurrentUser,
    code: str = Query(default=""),
    redirect_uri: str = Query(default=""),
    error: str | None = None,
    state: str | None = None,
) -> str:
    """OAuth callback: exchange the code, store credentials encrypted, done."""
    if error:
        return _page("Gmail connection failed", f"Google returned: {error}")
    if not code:
        return _page("Gmail connection failed", "Missing authorization code.")
    settings = get_settings()
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
        return _page("Gmail connection failed", "Google OAuth is not configured on the server.")
    uri = redirect_uri or settings.GOOGLE_REDIRECT_URI or f"{settings.BASE_URL}/api/integrations/gmail/callback"

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            token_resp = await client.post(
                _TOKEN_ENDPOINT,
                data={
                    "code": code,
                    "client_id": settings.GOOGLE_CLIENT_ID,
                    "client_secret": settings.GOOGLE_CLIENT_SECRET,
                    "redirect_uri": uri,
                    "grant_type": "authorization_code",
                },
            )
            token_data = token_resp.json()
            if token_resp.status_code != 200 or "access_token" not in token_data:
                return _page("Gmail connection failed", f"Token exchange error: {token_data.get('error_description', token_data.get('error', 'unknown'))}")
            info_resp = await client.get(f"{_USERINFO_ENDPOINT}?access_token={token_data['access_token']}")
            info = info_resp.json() if info_resp.status_code == 200 else {}
    except httpx.HTTPError as exc:
        return _page("Gmail connection failed", f"Network error during token exchange: {exc}")

    email = info.get("email") or ""
    token_json = json.dumps({
        "token": token_data.get("access_token", ""),
        "refresh_token": token_data.get("refresh_token", ""),
        "token_uri": _TOKEN_ENDPOINT,
        "client_id": settings.GOOGLE_CLIENT_ID,
        "client_secret": settings.GOOGLE_CLIENT_SECRET,
        "scopes": token_data.get("scope", " ".join(SCOPES)),
        "expiry": str(time.time() + int(token_data.get("expires_in", 3600))),
    })
    encrypted = encrypt_secret(token_json)
    expires_at = datetime.now(UTC) + timedelta(seconds=int(token_data.get("expires_in", 3600)))

    cred = (
        await db.execute(select(OAuthCredential).where(OAuthCredential.provider == "gmail",
                                                       OAuthCredential.account_email == email))
    ).scalars().first()
    if cred is None:
        cred = OAuthCredential(provider="gmail", account_email=email, scope=token_data.get("scope"),
                               token_encrypted=encrypted, expires_at=expires_at, is_active=True)
        db.add(cred)
    else:
        cred.token_encrypted = encrypted
        cred.expires_at = expires_at
        cred.is_active = True

    account = (await db.execute(select(EmailAccount).where(EmailAccount.email == email))).scalars().first()
    if account is None:
        account = EmailAccount(email=email, display_name=info.get("name") or email,
                               access_token_encrypted=encrypted, scope=token_data.get("scope"),
                               last_sync_at=datetime.now(UTC))
        db.add(account)
    else:
        account.access_token_encrypted = encrypted
        account.is_active = True
        account.last_sync_at = datetime.now(UTC)

    await audit.audit(db, actor=_user.username, action="integrations.gmail_connected", resource_type="email_account")
    await db.commit()
    return _page("Gmail connected", f"Connected account <b>{email}</b>. You can close this tab.")


def _page(title: str, detail: str) -> str:
    return (
        "<!doctype html><html><head><meta charset='utf-8'><title>Gmail connection</title></head>"
        "<body style='font-family:sans-serif;text-align:center;margin-top:80px'>"
        f"<h2>{title}</h2><p>{detail}</p>"
        "<p><a href='/'>Back to dashboard</a></p></body></html>"
    )


@router.post("/gmail/disconnect")
async def gmail_disconnect(
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: CurrentUser,
    _json: JsonRequest,
) -> dict:
    deleted_accounts = (
        await db.execute(delete(EmailAccount).where(EmailAccount.email.is_not(None)))
    ).rowcount or 0
    deleted_creds = (
        await db.execute(delete(OAuthCredential).where(OAuthCredential.provider == "gmail"))
    ).rowcount or 0
    await audit.audit(db, actor=_user.username, action="integrations.gmail_disconnected", resource_type="email_account")
    await db.commit()
    return {"disconnected": True, "accounts_removed": deleted_accounts, "credentials_removed": deleted_creds}


@router.get("/telegram/status")
async def telegram_status(_user: CurrentUser) -> dict:
    sender = TelegramSender()
    return {
        "configured": sender.enabled,
        "token_configured": bool(sender.token),
        "chat_id_configured": bool(sender.chat_id),
    }


@router.post("/telegram/test", response_model=TelegramTestResult)
async def telegram_test(
    _user: CurrentUser,
    _json: JsonRequest,
) -> TelegramTestResult:
    sender = TelegramSender()
    ok, detail = await sender.test()
    return TelegramTestResult(ok=ok, detail=detail)