"""Telegram Bot API integration (thin, typed, mockable)."""
from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger("app.services.telegram")

_BASE = "https://api.telegram.org"


class TelegramSender:
    """Sends notifications via the Telegram Bot API."""

    def __init__(self, token: str | None = None, chat_id: str | None = None) -> None:
        settings = get_settings()
        self.token = token or settings.TELEGRAM_BOT_TOKEN
        self.chat_id = str(chat_id or settings.TELEGRAM_CHAT_ID or "")

    @property
    def enabled(self) -> bool:
        return bool(self.token and self.chat_id)

    async def send(self, text: str, *, parse_mode: str = "HTML") -> tuple[bool, str]:
        """Send a text message. Returns (ok, detail)."""
        if not self.enabled:
            logger.warning("telegram_disabled message_not_sent chat_configured=%s", bool(self.chat_id))
            return False, "Telegram is not configured (set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)"
        payload: dict[str, Any] = {
            "chat_id": self.chat_id,
            "text": text[:4000],
            "disable_web_page_preview": False,
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(f"{_BASE}/bot{self.token}/sendMessage", json=payload)
                data = resp.json()
        except httpx.HTTPError as exc:
            logger.error("telegram_send_error detail=%s", str(exc))
            return False, str(exc)
        if resp.status_code == 200 and data.get("ok"):
            return True, "sent"
        return False, data.get("description", f"HTTP {resp.status_code}")

    async def test(self) -> tuple[bool, str]:
        """Verify the bot token and optionally send a hello to the chat."""
        if not self.token:
            return False, "TELEGRAM_BOT_TOKEN is not set"
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(f"{_BASE}/bot{self.token}/getMe")
                data = resp.json()
        except httpx.HTTPError as exc:
            return False, str(exc)
        if resp.status_code == 200 and data.get("ok"):
            me = data.get("result", {})
            if self.chat_id:
                ok, detail = await self.send(f"✅ Telegram connected as @{me.get('username', 'bot')}")
                return ok, detail
            return True, f"Bot @{me.get('username', 'bot')} is reachable (set TELEGRAM_CHAT_ID to enable alerts)"
        return False, data.get("description", f"HTTP {resp.status_code}")


def format_notification(
    title: str,
    body: str,
    vendor: str | None = None,
    company: str | None = None,
    email: str | None = None,
) -> str:
    """Build a short HTML-formatted Telegram message."""
    parts = [f"<b>{title}</b>"]
    if company:
        parts.append(f"Company: {company}")
    if vendor:
        parts.append(f"Vendor: {vendor}")
    if email:
        parts.append(f"Email: {email}")
    if body:
        parts.append(body)
    return "\n".join(parts)