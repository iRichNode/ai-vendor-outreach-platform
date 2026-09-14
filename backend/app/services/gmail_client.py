"""Gmail integration with Google OAuth and a transport abstraction.

The GmailTransport abstraction keeps the rest of the app testable without
network access: FakeTransport records sent messages for assertions.
"""
from __future__ import annotations

import base64
import logging
import time
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from typing import Any, Protocol

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.config import get_settings

logger = logging.getLogger("app.services.gmail")

SCOPES = ["https://www.googleapis.com/auth/gmail.send", "https://www.googleapis.com/auth/gmail.modify"]


class GmailTransport(Protocol):
    async def send_email(
        self,
        *,
        to: str,
        subject: str,
        body: str,
        reply_to: str | None = None,
        thread_id: str | None = None,
    ) -> dict[str, Any]:
        """Send an email. Returns {'ok': bool, 'id': str|None, 'detail': str}."""
        ...


def _build_message(
    *, to: str, subject: str, body: str, reply_to: str | None, thread_id: str | None,
    settings: Any | None = None,
) -> EmailMessage:
    settings = settings or get_settings()
    sender_name = settings.GMAIL_SENDER_NAME or settings.SMTP_FROM_NAME or "AI Vendor Outreach"
    sender_email = settings.GMAIL_SENDER_EMAIL or settings.SMTP_FROM_EMAIL or settings.SMTP_USERNAME
    msg = EmailMessage()
    msg["To"] = to
    msg["Subject"] = subject
    msg["From"] = formataddr((sender_name, sender_email))
    if reply_to:
        msg["Reply-To"] = reply_to
    if thread_id:
        msg["Thread-Id"] = thread_id
    msg["Message-ID"] = make_msgid()
    msg.set_content(
        body if settings.GMAIL_PLAIN_TEXT else _htmlify(body),
        subtype="text" if settings.GMAIL_PLAIN_TEXT else "html",
    )
    return msg


def _htmlify(text: str) -> str:
    import html

    escaped = html.escape(text).replace("\n", "<br>")
    return f"<html><body><div style='font-family:sans-serif'>{escaped}</div></body></html>"


class RealGmailTransport:
    """Send via the Gmail API using stored OAuth credentials."""

    def __init__(
        self, token_json: str | None = None, token_path: str | None = None, settings: Any | None = None
    ) -> None:
        self.token_json = token_json
        self.token_path = token_path
        self.settings = settings
        self._service: Any | None = None

    def _load_credentials(self) -> Credentials:
        if self.token_json:
            return Credentials.from_authorized_user_info(info=self.token_json, scopes=SCOPES)
        if self.token_path:
            return Credentials.from_authorized_user_file(self.token_path, scopes=SCOPES)
        raise RuntimeError("No Gmail token configured")

    def _get_service(self) -> Any:
        if self._service:
            return self._service
        creds = self._load_credentials()
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            if self.token_path:
                with open(self.token_path, "w") as fh:
                    fh.write(creds.to_json())
        self._service = build("gmail", "v1", credentials=creds, cache_discovery=False)
        return self._service

    async def send_email(
        self,
        *,
        to: str,
        subject: str,
        body: str,
        reply_to: str | None = None,
        thread_id: str | None = None,
    ) -> dict[str, Any]:
        msg = _build_message(
            to=to, subject=subject, body=body, reply_to=reply_to, thread_id=thread_id,
            settings=self.settings,
        )
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        try:
            svc = self._get_service()
            sent = svc.users().messages().send(userId="me", body={"raw": raw}).execute()
            return {"ok": True, "id": sent.get("id"), "detail": "sent"}
        except HttpError as exc:
            logger.error("gmail_send_error status=%s detail=%s", exc.resp.status, str(exc))
            return {"ok": False, "id": None, "detail": f"Gmail API error: {exc}"}
        except Exception as exc:  # noqa: BLE001 - surface any integration failure
            logger.error("gmail_send_error detail=%s", str(exc))
            return {"ok": False, "id": None, "detail": str(exc)}


class SmtpTransport:
    """Send via a plain SMTP server (Microsoft 365 / Outlook / any provider).

    Uses STARTTLS per SMTP_USE_TLS and authenticates when a username is set.
    Runs the blocking smtplib call inside a thread so the async worker is
    never blocked.
    """

    def __init__(self, settings: Any | None = None) -> None:
        self.settings = settings or get_settings()

    def _from_addr(self) -> str | None:
        return (
            self.settings.SMTP_FROM_EMAIL
            or self.settings.GMAIL_SENDER_EMAIL
            or self.settings.SMTP_USERNAME
            or None
        )

    def _send_blocking(self, to: str, msg: EmailMessage) -> None:
        import smtplib

        host = self.settings.SMTP_HOST or ("smtp.office365.com" if self.settings.SMTP_USERNAME else "")
        if not host:
            raise RuntimeError("SMTP host is not configured (set SMTP_HOST or gmail transport)")
        port = self.settings.SMTP_PORT or 587
        with smtplib.SMTP(host, port, timeout=30) as smtp:
            if self.settings.SMTP_USE_TLS:
                smtp.starttls()
            if self.settings.SMTP_USERNAME:
                smtp.login(self.settings.SMTP_USERNAME, self.settings.SMTP_PASSWORD or "")
            smtp.send_message(msg, from_addr=self._from_addr())

    async def send_email(
        self,
        *,
        to: str,
        subject: str,
        body: str,
        reply_to: str | None = None,
        thread_id: str | None = None,
    ) -> dict[str, Any]:
        import asyncio

        msg = _build_message(
            to=to, subject=subject, body=body, reply_to=reply_to, thread_id=thread_id,
            settings=self.settings,
        )
        try:
            await asyncio.to_thread(self._send_blocking, to, msg)
            return {"ok": True, "id": None, "detail": "sent via SMTP"}
        except Exception as exc:  # noqa: BLE001 - surface any integration failure
            logger.error("smtp_send_error detail=%s", str(exc))
            return {"ok": False, "id": None, "detail": f"SMTP error: {exc}"}


class FakeTransport:
    """In-memory transport: stores messages and returns deterministic ids."""

    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []
        self.fail_next = False

    async def send_email(
        self,
        *,
        to: str,
        subject: str,
        body: str,
        reply_to: str | None = None,
        thread_id: str | None = None,
    ) -> dict[str, Any]:
        if self.fail_next:
            self.fail_next = False
            return {"ok": False, "id": None, "detail": "injected failure"}
        record = {
            "to": to,
            "subject": subject,
            "body": body,
            "reply_to": reply_to,
            "thread_id": thread_id,
            "id": f"fake-{time.time_ns()}",
        }
        self.sent.append(record)
        return {"ok": True, "id": record["id"], "detail": "sent"}


def get_transport(transport_name: str = "", settings: Any | None = None) -> GmailTransport:
    """Return the transport configured by settings/transport_name.

    ``settings`` may be a runtime copy with panel-stored credentials merged in
    (see app.services.runtime_settings.effective_settings).
    """
    settings = settings or get_settings()
    name = transport_name or settings.GMAIL_TRANSPORT or "auto"
    if name == "fake":
        return FakeTransport()
    if settings.GMAIL_TOKEN_JSON or settings.GMAIL_TOKEN_FILE:
        return RealGmailTransport(
            token_json=settings.GMAIL_TOKEN_JSON,
            token_path=settings.GMAIL_TOKEN_FILE,
            settings=settings,
        )
    if name == "smtp":
        return SmtpTransport(settings)
    if name == "real":
        return RealGmailTransport(settings=settings)
    if name == "auto":
        if settings.SMTP_HOST:
            return SmtpTransport(settings)
    # auto with no credentials -> fake (demo mode; real send requires credentials)
    return FakeTransport()


def build_oauth_url(
    redirect_uri: str, client_id: str | None = None, settings: Any | None = None
) -> str:
    """Build a Google OAuth consent URL (no token exchange here)."""
    settings = settings or get_settings()
    flow = InstalledAppFlow.from_client_config(
        {
            "installed": {
                "client_id": client_id or settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [redirect_uri],
            }
        },
        scopes=SCOPES,
        redirect_uri=redirect_uri,
    )
    return flow.authorization_url()[0]