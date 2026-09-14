"""Meeting lifecycle: validation, human link entry, invitation sending."""
from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.conversation import Conversation
from app.models.enums import ConversationStatus, VendorStatus
from app.models.meeting import Meeting
from app.models.vendor import Vendor
from app.services import gmail_client, notifications, queue_service, vendor_service

logger = logging.getLogger("app.services.meeting")

_MEETING_URL_RE = re.compile(r"^(https?://)", re.I)
_ALLOWED_MEETING_HOSTS = {
    "zoom.us", "zoom.com", "meet.google.com", "teams.microsoft.com", "microsoft.com",
    "webex.com", "gotomeeting.com", "goto.com", "whereby.com", "meet.zoom.us",
    "calendly.com", "cal.com", "calendly.io",
}


def parse_meeting_url(raw: str | None) -> tuple[str | None, str | None]:
    """Validate a meeting URL. Returns (normalized_url, error)."""
    if not raw or not raw.strip():
        return None, "Meeting URL is required."
    candidate = raw.strip()
    if not _MEETING_URL_RE.match(candidate):
        candidate = f"https://{candidate}"
    try:
        parsed = urlparse(candidate)
    except ValueError as exc:
        return None, f"Invalid URL: {exc}"
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return None, "Meeting URL must be a valid http(s) URL."
    host = parsed.netloc.lower()
    for allowed in _ALLOWED_MEETING_HOSTS:
        if host == allowed or host.endswith(f".{allowed}"):
            return candidate, None
    # Unknown host: accept but warn (operator-confirmed links are trusted).
    logger.info("meeting_url_unrecognized_host host=%s", host)
    return candidate, None


async def create_or_update_meeting_request(
    db: AsyncSession, *, vendor: Vendor, conversation: Conversation | None = None,
    meeting_url: str | None = None, notes: str | None = None,
) -> Meeting:
    """Create/update a meeting record when a meeting is requested."""
    existing = None
    if conversation:
        existing = (
            await db.execute(
                select(Meeting)
                .where(Meeting.conversation_id == conversation.id, Meeting.status.in_(["REQUESTED", "WAITING_FOR_LINK", "LINK_RECEIVED"]))
                .order_by(Meeting.created_at.desc())
                .limit(1)
            )
        ).scalars().first()
    if existing is None:
        meeting = Meeting(
            vendor_id=vendor.id,
            campaign_id=conversation.campaign_id if conversation else None,
            conversation_id=conversation.id if conversation else None,
            meeting_url=None,
            status="REQUESTED",
            requested_time=datetime.now(UTC),
            notes=notes,
        )
        db.add(meeting)
        await db.flush()
        return meeting
    if meeting_url:
        normalized, error = parse_meeting_url(meeting_url)
        if error:
            raise ValueError(error)
        existing.meeting_url = normalized
        existing.status = "LINK_RECEIVED"
    if notes:
        existing.notes = notes
    await db.flush()
    return existing


async def register_vendor_meeting_link(
    db: AsyncSession, *, vendor: Vendor, conversation: Conversation | None, raw_url: str
) -> Meeting:
    """Operator (or validated inbound) link entry -> MEETING_LINK_RECEIVED."""
    normalized, error = parse_meeting_url(raw_url)
    if error:
        raise ValueError(error)
    meeting = await create_or_update_meeting_request(db, vendor=vendor, conversation=conversation, meeting_url=normalized)
    meeting.status = "LINK_RECEIVED"
    if conversation:
        conversation.status = ConversationStatus.WAITING_FOR_HUMAN_LINK.value  # operator still validates
    vendor.status = VendorStatus.MEETING_LINK_RECEIVED.value
    await notifications.notify_meeting_link_received(
        db,
        vendor_id=vendor.id,
        vendor_name=vendor.contact_name or vendor.company,
        company=vendor.company,
        email=vendor.email,
        conversation_id=conversation.id if conversation else None,
    )
    await db.flush()
    return meeting


async def send_invitation(
    db: AsyncSession,
    *,
    vendor: Vendor,
    meeting: Meeting,
    conversation: Conversation | None = None,
    transport: gmail_client.GmailTransport | None = None,
) -> dict:
    """Send the meeting invitation to the vendor via Gmail (MEETING_INVITATION job)."""
    settings = get_settings()
    if not meeting.meeting_url:
        return {"ok": False, "detail": "Meeting has no URL yet.", "message_id": None}
    sender = settings.GMAIL_SENDER_EMAIL or "outreach@example.com"
    subject = "Your meeting with our team"
    body = (
        f"Hi {vendor.contact_name or vendor.company},\n\n"
        f"Thanks for your interest! Here are the details for our meeting:\n\n"
        f"Link: {meeting.meeting_url}\n"
        f"{('Notes: ' + meeting.notes) if meeting.notes else ''}\n\n"
        f"Looking forward to it!\n\nBest regards,\n{settings.GMAIL_SENDER_NAME or 'The Outreach Team'}"
    )
    t = transport or gmail_client.get_transport()
    result = await t.send_email(to=vendor.email or "", subject=subject, body=body)
    if result["ok"]:
        meeting.status = "INVITATION_SENT"
        meeting.invitation_sent_at = datetime.now(UTC)
        if conversation:
            conversation.status = ConversationStatus.HUMAN_CONTROLLED.value
        vendor.status = VendorStatus.INVITATION_SENT.value
        vendor.meeting_status = "INVITATION_SENT"
        # Schedule follow-up to confirm/close after the meeting
        await queue_service.enqueue_job(
            db,
            job_type="MEETING_FOLLOWUP",
            vendor_id=vendor.id,
            campaign_id=meeting.campaign_id,
            conversation_id=meeting.conversation_id,
            run_after=datetime.now(UTC),
            idem_key=f"meeting-followup|{meeting.id}",
            payload={"meeting_id": meeting.id, "kind": "confirm"},
        )
        await db.flush()
    return {"ok": result["ok"], "detail": result.get("detail", ""), "message_id": result.get("id")}


async def mark_meeting_scheduled(db: AsyncSession, *, meeting: Meeting, vendor: Vendor, scheduled_time: datetime | None = None) -> None:
    meeting.status = "SCHEDULED"
    meeting.scheduled_time = scheduled_time or datetime.now(UTC)
    vendor.status = VendorStatus.MEETING_SCHEDULED.value
    vendor.meeting_status = "SCHEDULED"
    await db.flush()


async def complete_meeting(db: AsyncSession, *, meeting: Meeting, vendor: Vendor) -> None:
    meeting.status = "COMPLETED"
    vendor.status = VendorStatus.COMPLETED.value
    vendor.meeting_status = "COMPLETED"
    await db.flush()


async def cancel_meeting(db: AsyncSession, *, meeting: Meeting, vendor: Vendor, reason: str = "") -> None:
    meeting.status = "CANCELLED"
    meeting.notes = (meeting.notes + "\n" if meeting.notes else "") + f"Cancelled: {reason}"
    if vendor.status == VendorStatus.MEETING_SCHEDULED.value:
        vendor.status = VendorStatus.AI_CONVERSATION.value
    await db.flush()