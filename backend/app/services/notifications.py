"""Cross-channel outbound notifications: Telegram + in-app notifications."""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification
from app.services import telegram as telegram_service
from app.services.telegram import TelegramSender

logger = logging.getLogger("app.services.notifications")


async def notify(
    session: AsyncSession,
    *,
    title: str,
    body: str = "",
    severity: str = "info",
    notification_type: str = "INFO",
    vendor_id: str | None = None,
    conversation_id: str | None = None,
    vendor_name: str | None = None,
    company: str | None = None,
    email: str | None = None,
    link: str | None = None,
    send_telegram: bool = True,
    settings: Any | None = None,
) -> Notification:
    """Persist an in-app notification and optionally push to Telegram."""
    notif = Notification(
        notification_type=notification_type,
        title=title,
        body=body,
        vendor_id=vendor_id,
        conversation_id=conversation_id,
        severity=severity,
        read=False,
        telegram_sent=False,
        link=link,
        event_time=datetime.now(UTC),
    )
    session.add(notif)
    await session.flush()
    if send_telegram:
        sender = TelegramSender(settings=settings)
        if sender.enabled:
            text = telegram_service.format_notification(title, body, vendor=vendor_name, company=company, email=email)
            ok, detail = await sender.send(text)
            notif.telegram_sent = ok
            if not ok:
                notif.telegram_error = detail
        else:
            notif.telegram_error = "Telegram not configured; stored in-app only"
    return notif


async def notify_human_handoff(
    session: AsyncSession,
    *,
    vendor_id: str,
    vendor_name: str,
    company: str,
    email: str | None,
    reason: str,
    conversation_id: str | None = None,
    settings: Any | None = None,
) -> Notification:
    """Alert the operator that a campaign needs a human link/decision."""
    return await notify(
        session,
        title="Human handoff needed",
        body=f"{reason} Open the conversation to review and either mark INTERESTED -> request "
             f"meeting, or send a meeting link.",
        severity="warning",
        notification_type="HUMAN_REQUESTED",
        vendor_id=vendor_id,
        conversation_id=conversation_id,
        vendor_name=vendor_name,
        company=company,
        email=email,
        settings=settings,
    )


async def notify_meeting_link_received(
    session: AsyncSession,
    *,
    vendor_id: str,
    vendor_name: str,
    company: str,
    email: str | None,
    conversation_id: str | None = None,
) -> Notification:
    return await notify(
        session,
        title="Meeting link received",
        body="The vendor shared a meeting link. Validate it and send the invitation via Gmail.",
        severity="info",
        notification_type="MEETING_REQUEST",
        vendor_id=vendor_id,
        conversation_id=conversation_id,
        vendor_name=vendor_name,
        company=company,
        email=email,
    )


async def notify_ai_error(
    session: AsyncSession, *, vendor_id: str | None = None, detail: str, conversation_id: str | None = None
) -> Notification:
    return await notify(
        session,
        title="AI processing error",
        body=detail[:1000],
        severity="error",
        notification_type="ERROR",
        vendor_id=vendor_id,
        conversation_id=conversation_id,
    )


def notify_objects_payload(notif: Notification) -> dict[str, Any]:
    return {
        "id": notif.id,
        "notification_type": notif.notification_type,
        "title": notif.title,
        "body": notif.body,
        "severity": notif.severity,
        "read": notif.read,
        "telegram_sent": notif.telegram_sent,
        "telegram_error": notif.telegram_error,
        "vendor_id": notif.vendor_id,
        "conversation_id": notif.conversation_id,
        "link": notif.link,
        "event_time": notif.event_time.isoformat() if notif.event_time else None,
    }