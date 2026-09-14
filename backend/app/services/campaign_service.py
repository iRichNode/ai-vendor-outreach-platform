"""Campaign lifecycle: creation, vendor selection, activation, scheduling."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.campaign import Campaign, CampaignVendor
from app.models.conversation import Conversation
from app.models.enums import CampaignStatus, JobType, VendorStatus
from app.models.vendor import Vendor
from app.services.pacing import compute_pacing_sequence
from app.services.queue_service import count_pending_for, enqueue_job, idempotency_key_for


def _to_hhmm(value) -> str | None:
    if value is None:
        return None
    return f"{value.hour:02d}:{value.minute:02d}"


def apply_campaign_patch(campaign: Campaign, patch: dict[str, Any]) -> None:
    """Apply validated patch fields onto a Campaign ORM object."""
    for key, value in patch.items():
        if value is None:
            continue
        if key == "follow_ups":
            campaign.follow_ups = [item if isinstance(item, dict) else item.model_dump() for item in value]
        elif key == "qualification_questions":
            campaign.qualification_questions = (
                ", ".join(value) if isinstance(value, list) else value
            )
        elif key == "sending_start_time":
            campaign.sending_start_time = value
        elif key == "sending_end_time":
            campaign.sending_end_time = value
        elif key == "sending_days":
            campaign.sending_days = ",".join(str(d) for d in value) if isinstance(value, list) else value
        elif key == "ai_reply_mode":
            campaign.ai_reply_mode = value.value if hasattr(value, "value") else str(value)
        elif key == "vendor_ids":
            continue  # handled separately
        else:
            setattr(campaign, key, value)


def campaign_to_dict(campaign: Campaign) -> dict:
    return {
        "id": campaign.id,
        "name": campaign.name,
        "description": campaign.description,
        "status": campaign.status,
        "initial_email_subject": campaign.initial_email_subject,
        "initial_email_body": campaign.initial_email_body,
        "ai_instructions": campaign.ai_instructions,
        "qualification_questions": campaign.qualification_questions,
        "follow_ups": campaign.follow_ups or [],
        "batch_size": campaign.batch_size,
        "min_delay_minutes": campaign.min_delay_minutes,
        "max_delay_minutes": campaign.max_delay_minutes,
        "daily_max": campaign.daily_max,
        "sending_start_time": _to_hhmm(campaign.sending_start_time),
        "sending_end_time": _to_hhmm(campaign.sending_end_time),
        "sending_days": campaign.sending_days,
        "timezone": campaign.timezone,
        "ai_reply_mode": campaign.ai_reply_mode,
        "ai_reply_min_delay_minutes": campaign.ai_reply_min_delay_minutes,
        "ai_reply_max_delay_minutes": campaign.ai_reply_max_delay_minutes,
        "started_at": campaign.started_at.isoformat() if campaign.started_at else None,
        "completed_at": campaign.completed_at.isoformat() if campaign.completed_at else None,
        "created_at": campaign.created_at.isoformat() if campaign.created_at else None,
        # Avoid lazy-load in async context: only read the relation if it is already loaded.
        "vendor_count": len(campaign.campaign_vendors) if "campaign_vendors" in campaign.__dict__ else 0,
    }


async def add_vendors_to_campaign(db: AsyncSession, campaign: Campaign, vendor_ids: list[str]) -> int:
    existing = {
        cv.vendor_id for cv in (await db.execute(
            select(CampaignVendor).where(CampaignVendor.campaign_id == campaign.id)
        )).scalars().all()
    }
    added = 0
    for vid in vendor_ids:
        if vid in existing:
            continue
        if not await db.get(Vendor, vid):
            continue
        db.add(CampaignVendor(campaign_id=campaign.id, vendor_id=vid, added_at=datetime.now(UTC)))
        existing.add(vid)
        added += 1
    await db.flush()
    return added


async def schedule_initial_emails(db: AsyncSession, campaign: Campaign) -> int:
    """Compute pacing for all eligible slots and enqueue INITIAL_EMAIL jobs.

    Eligible = vendor READY_TO_CONTACT (or NEW/RESEARCHED -> moved to READY_TO_CONTACT),
    not opted out/bounced, no existing conversation with a sent initial email for this
    campaign. Idempotent per (campaign, vendor) via idempotency key.
    """
    slots = (
        await db.execute(
            select(CampaignVendor, Vendor)
            .join(Vendor, Vendor.id == CampaignVendor.vendor_id)
            .where(CampaignVendor.campaign_id == campaign.id)
        )
    ).all()

    eligible: list[tuple[CampaignVendor, Vendor]] = []
    for cv, vendor in slots:
        if vendor.opted_out or vendor.bounced:
            continue
        if vendor.status not in (VendorStatus.NEW.value, VendorStatus.RESEARCHED.value,
                                 VendorStatus.READY_TO_CONTACT.value, VendorStatus.CONTACTED.value):
            continue
        if await count_pending_for(db, vendor_id=vendor.id, campaign_id=campaign.id,
                                   job_type=JobType.INITIAL_EMAIL.value):
            continue
        # Skip vendors already sent an initial email in this campaign
        key = idempotency_key_for(JobType.INITIAL_EMAIL.value, vendor.id, campaign.id)
        existing = await db.execute(
            select(Conversation.id).where(Conversation.vendor_id == vendor.id,
                                          Conversation.campaign_id == campaign.id)
        )
        if existing.scalars().first():
            continue
        eligible.append((cv, vendor))

    if not eligible:
        return 0

    start = campaign.started_at or datetime.now(UTC)
    timings = compute_pacing_sequence(campaign, len(eligible), start)
    enqueued = 0
    for (cv, vendor), run_at in zip(eligible, timings):
        if vendor.status in (VendorStatus.NEW.value, VendorStatus.RESEARCHED.value):
            vendor.status = VendorStatus.READY_TO_CONTACT.value
        await enqueue_job(
            db,
            job_type=JobType.INITIAL_EMAIL.value,
            vendor_id=vendor.id,
            campaign_id=campaign.id,
            run_after=run_at,
            payload={
                "subject": campaign.initial_email_subject,
                "body": campaign.initial_email_body,
                "campaign_name": campaign.name,
                "ai_instructions": campaign.ai_instructions,
            },
            idem_key=idempotency_key_for(JobType.INITIAL_EMAIL.value, vendor.id, campaign.id),
        )
        cv.status = "SCHEDULED"
        enqueued += 1
    await db.flush()
    return enqueued


async def schedule_follow_up(db: AsyncSession, *, conversation_id: str, campaign: Campaign | None,
                             vendor_id: str, step: int, base_time: datetime | None = None) -> bool:
    """Schedule the next follow-up (1-indexed step) for a conversation."""
    if not campaign or not campaign.follow_ups:
        return False
    follow_ups = campaign.follow_ups
    if step > len(follow_ups):
        return False
    item = follow_ups[step - 1]
    base = base_time or datetime.now(UTC)
    run_at = base + timedelta(days=item["days_after"])
    await enqueue_job(
        db,
        job_type=JobType.FOLLOW_UP.value,
        vendor_id=vendor_id,
        campaign_id=campaign.id,
        conversation_id=conversation_id,
        run_after=run_at,
        payload={"subject": item["subject"], "body": item["body"], "step": step},
        idem_key=idempotency_key_for(JobType.FOLLOW_UP.value, vendor_id, campaign.id, conversation_id, step),
        step=step,
    )
    return True