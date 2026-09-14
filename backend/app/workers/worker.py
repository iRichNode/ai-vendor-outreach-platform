"""Persistent outbound worker.

Claims due jobs from the database queue (PostgreSQL SKIP LOCKED, idempotent by
idempotency_key) and dispatches them through the same services the API uses.
A worker restart never duplicates mail: a job can only be claimed/completed once.

Run:
    python -m app.workers.worker
"""
from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import create_engine_and_session
from app.models.conversation import Conversation
from app.models.enums import ConversationStatus, MessageDirection, MessageOrigin, VendorStatus
from app.models.message import Message
from app.models.vendor import Vendor
from app.services import campaign_service, conversation_service, meeting_service, queue_service
from app.services.gmail_client import get_transport

logger = logging.getLogger("app.worker")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


async def _handle_initial_email(db: AsyncSession, job) -> None:
    vendor = await db.get(Vendor, job.vendor_id)
    if not vendor:
        raise RuntimeError(f"Vendor {job.vendor_id} not found")
    if vendor.opted_out or vendor.bounced:
        raise RuntimeError(f"Vendor {vendor.email} opted out or bounced; will not send")
    payload = job.payload or {}
    subject = payload.get("subject") or "Introduction"
    body = payload.get("body") or ""
    if not vendor.email:
        raise RuntimeError("Vendor has no email address")

    transport = get_transport()
    result = await transport.send_email(to=vendor.email, subject=subject, body=body)
    if not result["ok"]:
        raise RuntimeError(result.get("detail") or "Gmail send failed")

    convo = await conversation_service.get_or_create_conversation(
        db, vendor_id=vendor.id, campaign_id=job.campaign_id, subject=subject
    )
    msg = Message(
        conversation_id=convo.id,
        vendor_id=vendor.id,
        idempotency_key=f"out-{job.id}",
        sender=conversation_service.recipient_addr(vendor),
        recipient=vendor.email,
        subject=subject,
        body=body,
        received_at=datetime.now(UTC),
        direction=MessageDirection.OUTBOUND.value,
        origin=MessageOrigin.AI.value,
        ai_used=False,
        draft=False,
        delivery_state="SENT",
    )
    db.add(msg)
    convo.last_outbound_at = datetime.now(UTC)
    vendor.last_contacted_at = datetime.now(UTC)
    vendor.status = VendorStatus.CONTACTED.value
    if job.campaign_id:
        cv = (
            await db.execute(
                select(campaign_service.CampaignVendor).where(
                    campaign_service.CampaignVendor.campaign_id == job.campaign_id,
                    campaign_service.CampaignVendor.vendor_id == vendor.id,
                )
            )
        ).scalars().first()
        if cv:
            cv.status = "EMAILED"
        campaign = await db.get(campaign_service.Campaign, job.campaign_id)
        if campaign:
            await campaign_service.schedule_follow_up(
                db, conversation_id=convo.id, campaign=campaign, vendor_id=vendor.id, step=1
            )
    await db.flush()


async def _handle_follow_up(db: AsyncSession, job) -> None:
    vendor = await db.get(Vendor, job.vendor_id)
    if not vendor:
        raise RuntimeError(f"Vendor {job.vendor_id} not found")
    if vendor.opted_out or vendor.bounced:
        raise RuntimeError(f"Vendor opted out or bounced; skipping follow-up")
    if not vendor.email:
        raise RuntimeError("Vendor has no email address")
    payload = job.payload or {}
    subject = payload.get("subject") or "Following up"
    body = payload.get("body") or ""

    convo = None
    if job.conversation_id:
        convo = await db.get(Conversation, job.conversation_id)
    if convo is None:
        convo = await conversation_service.get_or_create_conversation(
            db, vendor_id=vendor.id, campaign_id=job.campaign_id, subject=subject
        )

    transport = get_transport()
    result = await transport.send_email(
        to=vendor.email, subject=conversation_service.subject_reply(subject), body=body,
        thread_id=convo.gmail_thread_id,
    )
    if not result["ok"]:
        raise RuntimeError(result.get("detail") or "Gmail send failed")

    msg = Message(
        conversation_id=convo.id,
        vendor_id=vendor.id,
        idempotency_key=f"out-{job.id}",
        sender=conversation_service.recipient_addr(vendor),
        recipient=vendor.email,
        subject=conversation_service.subject_reply(subject),
        body=body,
        received_at=datetime.now(UTC),
        direction=MessageDirection.OUTBOUND.value,
        origin=MessageOrigin.AI.value,
        ai_used=False,
        draft=False,
        delivery_state="SENT",
    )
    db.add(msg)
    convo.last_outbound_at = datetime.now(UTC)
    vendor.last_contacted_at = datetime.now(UTC)
    if vendor.status in (VendorStatus.NEW.value, VendorStatus.RESEARCHED.value,
                         VendorStatus.READY_TO_CONTACT.value):
        vendor.status = VendorStatus.CONTACTED.value
    # chain the next follow-up
    if job.campaign_id:
        campaign = await db.get(campaign_service.Campaign, job.campaign_id)
        if campaign:
            next_step = (job.step or 1) + 1
            await campaign_service.schedule_follow_up(
                db, conversation_id=convo.id, campaign=campaign,
                vendor_id=vendor.id, step=next_step, base_time=datetime.now(UTC),
            )
    await db.flush()


async def _handle_ai_reply(db: AsyncSession, job) -> None:
    payload = job.payload or {}
    conversation = await db.get(Conversation, payload.get("conversation_id", job.conversation_id))
    vendor = await db.get(Vendor, job.vendor_id)
    if not conversation or not vendor:
        raise RuntimeError("Conversation or vendor not found for AI_REPLY job")
    if conversation.ai_paused or vendor.opted_out:
        return  # nothing to do; operator/vendor decision wins
    inbound = None
    if payload.get("inbound_message_id"):
        from app.models.message import Message

        inbound = await db.get(Message, payload["inbound_message_id"])
    if inbound is None:
        from sqlalchemy import desc

        inbound = (
            await db.execute(
                select(Message)
                .where(Message.conversation_id == conversation.id,
                       Message.direction == MessageDirection.INBOUND.value)
                .order_by(desc(Message.received_at))
                .limit(1)
            )
        ).scalars().first()
    if inbound is None:
        raise RuntimeError("No inbound message to reply to")
    result = await conversation_service.decide_and_apply(db, conversation=conversation, vendor=vendor,
                                                         inbound=inbound)
    if result.get("reply_message_id") and not vendor.opted_out:
        if job.campaign_id:
            campaign = await db.get(campaign_service.Campaign, job.campaign_id)
            if campaign:
                await campaign_service.schedule_follow_up(
                    db, conversation_id=conversation.id, campaign=campaign,
                    vendor_id=vendor.id, step=(conversation.follow_up_step or 0) + 1,
                )
    await db.flush()


async def _handle_meeting_invitation(db: AsyncSession, job) -> None:
    payload = job.payload or {}
    from app.models.meeting import Meeting as MeetingModel

    meeting = await db.get(MeetingModel, payload.get("meeting_id", job.conversation_id))
    if meeting is None:
        raise RuntimeError("Meeting not found for invitation")
    vendor = await db.get(Vendor, meeting.vendor_id)
    if not vendor:
        raise RuntimeError("Vendor not found for meeting invitation")
    result = await meeting_service.send_invitation(db, vendor=vendor, meeting=meeting)
    if not result["ok"]:
        raise RuntimeError(result["detail"])
    await db.flush()


async def _handle_meeting_followup(db: AsyncSession, job) -> None:
    payload = job.payload or {}
    from app.models.meeting import Meeting as MeetingModel

    meeting = await db.get(MeetingModel, payload.get("meeting_id", ""))
    vendor = await db.get(Vendor, job.vendor_id)
    if meeting is None or not vendor:
        raise RuntimeError("Meeting or vendor not found for meeting follow-up")
    if not vendor.email:
        raise RuntimeError("Vendor has no email address")
    transport = get_transport()
    subject = "Did our meeting happen?"
    body = (
        f"Hi {vendor.contact_name or vendor.company},\n\n"
        f"Thanks again for the call! Could you confirm the meeting took place "
        f"and whether you would like to continue?\n\nBest regards,\nThe Outreach Team"
    )
    result = await transport.send_email(to=vendor.email, subject=subject, body=body)
    if not result["ok"]:
        raise RuntimeError(result.get("detail") or "Gmail send failed")
    convo = None
    if meeting.conversation_id:
        convo = await db.get(Conversation, meeting.conversation_id)
    if convo is not None:
        msg = Message(
            conversation_id=convo.id,
            vendor_id=vendor.id,
            idempotency_key=f"out-{job.id}",
            sender=conversation_service.recipient_addr(vendor),
            recipient=vendor.email,
            subject=subject,
            body=body,
            received_at=datetime.now(UTC),
            direction=MessageDirection.OUTBOUND.value,
            origin=MessageOrigin.AI.value,
            ai_used=False,
            draft=False,
        )
        db.add(msg)
        convo.last_outbound_at = datetime.now(UTC)
    vendor.last_contacted_at = datetime.now(UTC)
    await db.flush()


_HANDLERS = {
    "INITIAL_EMAIL": _handle_initial_email,
    "FOLLOW_UP": _handle_follow_up,
    "AI_REPLY": _handle_ai_reply,
    "MEETING_INVITATION": _handle_meeting_invitation,
    "MEETING_FOLLOWUP": _handle_meeting_followup,
}


async def _process_job(db: AsyncSession, job) -> None:
    handler = _HANDLERS.get(job.job_type)
    if handler is None:
        raise RuntimeError(f"Unknown job_type: {job.job_type}")
    try:
        await handler(db, job)
        await queue_service.complete_job(db, job, error=None)
    except Exception as exc:  # noqa: BLE001 - worker must survive any single failure
        logger.exception("job_failed job_id=%s type=%s", job.id, job.job_type)
        await queue_service.complete_job(db, job, error=str(exc)[:2000])
    finally:
        await db.commit()


async def run_once(interval_seconds: int = 5) -> None:
    """One worker cycle: claim due jobs and dispatch them."""
    _, session_factory = create_engine_and_session()
    async with session_factory() as db:
        if await queue_service.is_global_paused(db):
            return
        jobs = await queue_service.claim_jobs(db, limit=get_settings().SEND_BATCH_SIZE or 5)
        for job in jobs:
            await _process_job(db, job)


async def main() -> None:
    settings = get_settings()
    interval = settings.DISPATCH_INTERVAL_SECONDS or 15
    logger.info("worker started interval_seconds=%s", interval)
    while True:
        try:
            await run_once()
        except Exception as exc:  # noqa: BLE001
            logger.exception("worker_cycle_error detail=%s", str(exc))
        await asyncio.sleep(interval)


if __name__ == "__main__":
    asyncio.run(main())