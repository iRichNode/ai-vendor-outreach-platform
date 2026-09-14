"""Vendor creation, normalization, deduplication and state transitions."""
from __future__ import annotations

import re
from urllib.parse import urlparse

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import QualificationStatus, VendorStatus
from app.models.vendor import Vendor

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalize_email(email: str | None) -> str | None:
    if not email:
        return None
    email = email.strip().lower()
    return email if EMAIL_RE.fullmatch(email) else None


def normalize_website(website: str | None) -> str | None:
    if not website:
        return None
    website = website.strip()
    if not website.startswith(("http://", "https://")):
        website = f"https://{website}"
    try:
        parsed = urlparse(website)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            return None
    except ValueError:
        return None
    return website


def email_domain(email: str | None) -> str | None:
    email = normalize_email(email)
    if not email:
        return None
    return email.rsplit("@", 1)[1].lower()


def company_loc_key(company: str, city: str | None, state: str | None) -> str:
    norm = re.sub(r"[^a-z0-9]+", "", (company or "").lower()).strip()
    city_n = re.sub(r"[^a-z0-9]+", "", (city or "").lower())
    state_n = re.sub(r"[^a-z0-9]+", "", (state or "").lower())
    return f"{norm}|{city_n}|{state_n}" if (city_n or state_n) else f"{norm}|*"


async def find_duplicate_vendor(db: AsyncSession, *, company: str, email: str | None, website: str | None,
                                city: str | None, state: str | None, except_id: str | None = None) -> Vendor | None:
    """Return an existing vendor that would be a duplicate.

    Checks (normalized): email, domain, company+location.
    """
    stmt = select(Vendor)

    conditions = []
    norm_email = normalize_email(email or "")
    norm_website = normalize_website(website or "")
    if norm_email:
        conditions.append(Vendor.normalized_email == norm_email)
        conditions.append(Vendor.email_domain == email_domain(norm_email))
    if norm_website:
        domain = urlparse(norm_website).netloc.removeprefix("www.").lower()
        if domain:
            conditions.append(or_(Vendor.email_domain == domain, Vendor.website.like(f"%%{domain}%%")))
    if company:
        key = company_loc_key(company, city, state)
        conditions.append(Vendor.company_loc_key == key)

    if not conditions:
        return None
    stmt = stmt.where(or_(*conditions))
    if except_id:
        stmt = stmt.where(Vendor.id != except_id)
    return (await db.execute(stmt.limit(1))).scalars().first()


async def create_vendor(db: AsyncSession, data: dict) -> Vendor:
    company = (data.get("company") or "").strip()
    if not company:
        raise ValueError("Company is required")
    email = normalize_email(data.get("email"))
    website = normalize_website(data.get("website"))
    duplicate = await find_duplicate_vendor(
        db, company=company, email=email, website=website,
        city=data.get("city"), state=data.get("state"),
    )
    if duplicate:
        raise ValueError(f"Duplicate vendor: {duplicate.company} ({duplicate.email or duplicate.website or 'no contact'}) already exists")

    tags = data.get("tags")
    status = data.get("status") or VendorStatus.NEW.value

    vendor = Vendor(
        company=company,
        contact_name=(data.get("contact_name") or "").strip() or None,
        email=email,
        phone=(data.get("phone") or "").strip() or None,
        website=website,
        address=(data.get("address") or "").strip() or None,
        city=(data.get("city") or "").strip() or None,
        state=(data.get("state") or "").strip() or None,
        country=(data.get("country") or "").strip() or None,
        trade=(data.get("trade") or "").strip() or None,
        source=data.get("source") or "MANUAL",
        source_url=(data.get("source_url") or "").strip() or None,
        notes=data.get("notes"),
        tags=",".join(tags) if tags else None,
        normalized_email=email,
        email_domain=email_domain(email),
        company_loc_key=company_loc_key(company, data.get("city"), data.get("state")),
        status=status,
        qualification_status=data.get("qualification_status") or QualificationStatus.UNQUALIFIED.value,
    )
    db.add(vendor)
    await db.flush()
    return vendor


# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------

_TRANSITIONS: dict[VendorStatus, set[VendorStatus]] = {
    VendorStatus.NEW: {VendorStatus.RESEARCHED, VendorStatus.READY_TO_CONTACT, VendorStatus.NOT_INTERESTED, VendorStatus.OPTED_OUT, VendorStatus.BOUNCED},
    VendorStatus.RESEARCHED: {VendorStatus.NEW, VendorStatus.READY_TO_CONTACT, VendorStatus.NOT_INTERESTED, VendorStatus.OPTED_OUT, VendorStatus.BOUNCED},
    VendorStatus.READY_TO_CONTACT: {VendorStatus.CONTACTED, VendorStatus.NEW, VendorStatus.RESEARCHED, VendorStatus.NOT_INTERESTED, VendorStatus.OPTED_OUT, VendorStatus.BOUNCED},
    VendorStatus.CONTACTED: {VendorStatus.REPLIED, VendorStatus.AI_CONVERSATION, VendorStatus.INTERESTED, VendorStatus.QUALIFYING, VendorStatus.QUALIFIED, VendorStatus.MEETING_REQUESTED, VendorStatus.WAITING_FOR_HUMAN_LINK, VendorStatus.HUMAN_HANDOFF, VendorStatus.NOT_INTERESTED, VendorStatus.OPTED_OUT, VendorStatus.BOUNCED, VendorStatus.READY_TO_CONTACT},
    VendorStatus.REPLIED: {VendorStatus.AI_CONVERSATION, VendorStatus.INTERESTED, VendorStatus.QUALIFYING, VendorStatus.QUALIFIED, VendorStatus.MEETING_REQUESTED, VendorStatus.WAITING_FOR_HUMAN_LINK, VendorStatus.HUMAN_HANDOFF, VendorStatus.NOT_INTERESTED, VendorStatus.OPTED_OUT, VendorStatus.BOUNCED, VendorStatus.CONTACTED},
    VendorStatus.AI_CONVERSATION: {VendorStatus.REPLIED, VendorStatus.INTERESTED, VendorStatus.QUALIFYING, VendorStatus.QUALIFIED, VendorStatus.MEETING_REQUESTED, VendorStatus.WAITING_FOR_HUMAN_LINK, VendorStatus.MEETING_LINK_RECEIVED, VendorStatus.INVITATION_SENT, VendorStatus.MEETING_SCHEDULED, VendorStatus.HUMAN_HANDOFF, VendorStatus.NOT_INTERESTED, VendorStatus.OPTED_OUT, VendorStatus.BOUNCED, VendorStatus.COMPLETED},
    VendorStatus.INTERESTED: {VendorStatus.QUALIFYING, VendorStatus.QUALIFIED, VendorStatus.MEETING_REQUESTED, VendorStatus.WAITING_FOR_HUMAN_LINK, VendorStatus.HUMAN_HANDOFF, VendorStatus.NOT_INTERESTED, VendorStatus.OPTED_OUT, VendorStatus.BOUNCED, VendorStatus.AI_CONVERSATION, VendorStatus.REPLIED},
    VendorStatus.QUALIFYING: {VendorStatus.QUALIFIED, VendorStatus.INTERESTED, VendorStatus.MEETING_REQUESTED, VendorStatus.WAITING_FOR_HUMAN_LINK, VendorStatus.HUMAN_HANDOFF, VendorStatus.NOT_INTERESTED, VendorStatus.OPTED_OUT, VendorStatus.BOUNCED, VendorStatus.AI_CONVERSATION},
    VendorStatus.QUALIFIED: {VendorStatus.MEETING_REQUESTED, VendorStatus.WAITING_FOR_HUMAN_LINK, VendorStatus.HUMAN_HANDOFF, VendorStatus.INTERESTED, VendorStatus.NOT_INTERESTED, VendorStatus.OPTED_OUT, VendorStatus.BOUNCED, VendorStatus.INVITATION_SENT, VendorStatus.MEETING_SCHEDULED, VendorStatus.COMPLETED},
    VendorStatus.MEETING_REQUESTED: {VendorStatus.WAITING_FOR_HUMAN_LINK, VendorStatus.HUMAN_HANDOFF, VendorStatus.INTERESTED, VendorStatus.QUALIFIED, VendorStatus.NOT_INTERESTED, VendorStatus.OPTED_OUT, VendorStatus.BOUNCED, VendorStatus.COMPLETED},
    VendorStatus.WAITING_FOR_HUMAN_LINK: {VendorStatus.MEETING_LINK_RECEIVED, VendorStatus.HUMAN_HANDOFF, VendorStatus.MEETING_REQUESTED, VendorStatus.INTERESTED, VendorStatus.NOT_INTERESTED, VendorStatus.OPTED_OUT},
    VendorStatus.MEETING_LINK_RECEIVED: {VendorStatus.INVITATION_SENT, VendorStatus.MEETING_SCHEDULED, VendorStatus.HUMAN_HANDOFF, VendorStatus.MEETING_REQUESTED, VendorStatus.WAITING_FOR_HUMAN_LINK, VendorStatus.OPTED_OUT},
    VendorStatus.INVITATION_SENT: {VendorStatus.MEETING_SCHEDULED, VendorStatus.HUMAN_HANDOFF, VendorStatus.OPTED_OUT, VendorStatus.NOT_INTERESTED, VendorStatus.MEETING_REQUESTED},
    VendorStatus.MEETING_SCHEDULED: {VendorStatus.COMPLETED, VendorStatus.HUMAN_HANDOFF, VendorStatus.OPTED_OUT, VendorStatus.NOT_INTERESTED, VendorStatus.INVITATION_SENT},
    VendorStatus.HUMAN_HANDOFF: {VendorStatus.AI_CONVERSATION, VendorStatus.REPLIED, VendorStatus.INTERESTED, VendorStatus.QUALIFIED, VendorStatus.MEETING_LINK_RECEIVED, VendorStatus.INVITATION_SENT, VendorStatus.MEETING_SCHEDULED, VendorStatus.COMPLETED, VendorStatus.NOT_INTERESTED, VendorStatus.OPTED_OUT, VendorStatus.READY_TO_CONTACT},
    VendorStatus.COMPLETED: {VendorStatus.MEETING_SCHEDULED, VendorStatus.HUMAN_HANDOFF, VendorStatus.ARCHIVED if hasattr(VendorStatus, "ARCHIVED") else VendorStatus.COMPLETED},
    VendorStatus.NOT_INTERESTED: {VendorStatus.READY_TO_CONTACT, VendorStatus.OPTED_OUT, VendorStatus.AI_CONVERSATION},
    VendorStatus.OPTED_OUT: {VendorStatus.READY_TO_CONTACT},
    VendorStatus.BOUNCED: {VendorStatus.READY_TO_CONTACT, VendorStatus.NEW},
}

# Explicit opt-out terminal shortcut
_FORCE_ALLOWED_FROM = {
    VendorStatus.NEW, VendorStatus.RESEARCHED, VendorStatus.READY_TO_CONTACT, VendorStatus.CONTACTED,
    VendorStatus.REPLIED, VendorStatus.AI_CONVERSATION, VendorStatus.INTERESTED, VendorStatus.QUALIFYING,
    VendorStatus.QUALIFIED, VendorStatus.MEETING_REQUESTED, VendorStatus.WAITING_FOR_HUMAN_LINK,
    VendorStatus.MEETING_LINK_RECEIVED, VendorStatus.INVITATION_SENT, VendorStatus.MEETING_SCHEDULED,
    VendorStatus.HUMAN_HANDOFF, VendorStatus.COMPLETED,
}


def can_transition(current: str, target: str) -> bool:
    try:
        cur = VendorStatus(current)
        tgt = VendorStatus(target)
    except ValueError:
        return False
    if tgt in (VendorStatus.OPTED_OUT, VendorStatus.BOUNCED) and cur in _FORCE_ALLOWED_FROM:
        return True
    return tgt in _TRANSITIONS.get(cur, set())


async def transition_vendor(db: AsyncSession, vendor: Vendor, target: str, *, force: bool = False) -> bool:
    """Apply a status transition; returns False when not allowed (unless force)."""
    if vendor.opted_out and target != VendorStatus.OPTED_OUT.value and not force:
        return False
    if vendor.status == target:
        return True
    if not (force or can_transition(vendor.status, target)):
        return False
    vendor.status = target
    if target == VendorStatus.OPTED_OUT.value:
        vendor.opted_out = True
    if target in (VendorStatus.CONTACTED.value, VendorStatus.REPLIED.value, VendorStatus.AI_CONVERSATION.value,
                  VendorStatus.INTERESTED.value, VendorStatus.QUALIFYING.value, VendorStatus.QUALIFIED.value):
        from datetime import UTC, datetime
        vendor.last_contacted_at = datetime.now(UTC)
    await db.flush()
    return True