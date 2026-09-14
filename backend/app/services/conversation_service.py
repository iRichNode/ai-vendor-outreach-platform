"""Conversation state machine + AI reply orchestration.

The AI proposes; the backend decides. Every inbound message flows through:

  1. record_message()      -> persisted with idempotency
  2. decide_action()       -> AI suggests intent/qualification/reply
  3. apply_decision()      -> backend validates and applies state transitions

Only allowed transitions in the vendor state machine are applied. The AI never
executes commands; it only produces structured decisions interpreted here.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation
from app.models.enums import (
    ConversationStatus,
    MessageDirection,
    MessageOrigin,
    VendorStatus,
)
from app.models.message import Message
from app.models.vendor import Vendor
from app.services import ai as ai_service
from app.services import notifications, queue_service, vendor_service

logger = logging.getLogger("app.services.conversation")

# Backend decides when human involvement is required (never the LLM).
_HUMAN_NEEDED_FOR_INBOUND = {
    "request_meeting": True,  # scheduling requires a real calendar/link
    "needs_more_info": False,
    "ask_question": False,
    "interested": False,      # qualification happens through conversation
    "not_interested": False,
    "opt_out": False,
    "request_human": True,
    "other": False,
}

_STATUS_BY_INTENT: dict[str, VendorStatus] = {
    "interested": VendorStatus.INTERESTED,
    "not_interested": VendorStatus.NOT_INTERESTED,
    "opt_out": VendorStatus.OPTED_OUT,
    "request_human": VendorStatus.HUMAN_HANDOFF,
    "request_meeting": VendorStatus.MEETING_REQUESTED,
    "ask_question": VendorStatus.AI_CONVERSATION,
    "needs_more_info": VendorStatus.AI_CONVERSATION,
    "other": VendorStatus.AI_CONVERSATION,
}


async def record_message(
    db: AsyncSession,
    *,
    conversation_id: str,
    vendor_id: str,
    sender: str,
    recipient: str,
    subject: str | None,
    body: str,
    body_html: str | None,
    direction: str,
    origin: str,
    gmail_message_id: str | None = None,
    gmail_thread_id: str | None = None,
    idempotency_key: str | None = None,
    received_at: datetime | None = None,
) -> Message | None:
    """Persist a message. Returns None when the idempotency key already exists."""
    key = idempotency_key or f"msg-{gmail_message_id or uuid4_hex()}"
    existing = (await db.execute(select(Message).where(Message.idempotency_key == key))).scalars().first()
    if existing:
        return None
    msg = Message(
        conversation_id=conversation_id,
        vendor_id=vendor_id,
        gmail_message_id=gmail_message_id,
        gmail_thread_id=gmail_thread_id,
        idempotency_key=key,
        sender=sender,
        recipient=recipient,
        subject=subject,
        body=body,
        body_html=body_html,
        received_at=received_at or datetime.now(UTC),
        direction=direction,
        origin=origin,
        ai_used=False,
        draft=False,
    )
    db.add(msg)
    await db.flush()
    return msg


async def get_or_create_conversation(
    db: AsyncSession, *, vendor_id: str, campaign_id: str | None = None, subject: str | None = None
) -> Conversation:
    active = (
        await db.execute(
            select(Conversation)
            .where(Conversation.vendor_id == vendor_id, Conversation.status != "ARCHIVED")
            .order_by(Conversation.created_at.desc())
            .limit(1)
        )
    ).scalars().first()
    if active:
        return active
    convo = Conversation(
        vendor_id=vendor_id,
        campaign_id=campaign_id,
        subject=subject,
        status=ConversationStatus.ACTIVE.value,
    )
    db.add(convo)
    await db.flush()
    return convo


async def handle_inbound(
    db: AsyncSession,
    *,
    vendor_id: str,
    sender: str,
    recipient: str,
    subject: str | None,
    body: str,
    body_html: str | None,
    gmail_message_id: str,
    gmail_thread_id: str | None,
) -> dict[str, Any]:
    """Full inbound pipeline: store -> analyze -> decide -> apply."""
    vendor = (await db.execute(select(Vendor).where(Vendor.id == vendor_id))).scalars().first()
    if not vendor:
        raise ValueError(f"Unknown vendor: {vendor_id}")
    convo = await get_or_create_conversation(db, vendor_id=vendor_id, subject=subject)
    msg = await record_message(
        db,
        conversation_id=convo.id,
        vendor_id=vendor_id,
        sender=sender,
        recipient=recipient,
        subject=subject,
        body=body,
        body_html=body_html,
        direction=MessageDirection.INBOUND.value,
        origin=MessageOrigin.VENDOR.value,
        gmail_message_id=gmail_message_id,
        gmail_thread_id=gmail_thread_id,
    )
    if msg is None:
        return {"duplicate": True, "message": None}
    convo.last_inbound_at = datetime.now(UTC)
    vendor.last_reply_at = datetime.now(UTC)
    await db.flush()
    return {"duplicate": False, "conversation": convo, "message": msg}


async def decide_and_apply(
    db: AsyncSession, *, conversation: Conversation, vendor: Vendor, inbound: Message,
    settings: Any | None = None,
) -> dict[str, Any]:
    """Ask the AI for a decision, then apply it with backend guardrails."""
    llm = ai_service.build_llm(settings=settings)
    prompt_user = f"Subject: {inbound.subject or ''}\nBody: {inbound.body[:6000]}"
    decision = await llm.decide(_SYSTEM_PROMPT, prompt_user)

    # Guardrail 1: PII / secrets must never be echoed
    safe_reply, flagged = ai_service.guardrail_check(decision.response)
    decision.response = safe_reply

    # Guardrail 2: backend decides human involvement
    needs_human = decision.needs_human or _HUMAN_NEEDED_FOR_INBOUND.get(decision.intent, False)

    vendor_updated = False
    if decision.intent == "opt_out":
        vendor.opted_out = True
        vendor.opted_out_at = datetime.now(UTC)
        vendor.status = VendorStatus.OPTED_OUT.value
        vendor_updated = True
        conversation.ai_paused = True
    else:
        target_status = _STATUS_BY_INTENT.get(decision.intent)
        if target_status:
            ok = vendor_service.transition_vendor(db, vendor, target_status.value, force=False)
            if not ok:
                # Fall back to permissive AI_CONVERSATION so replies still work
                vendor.status = VendorStatus.AI_CONVERSATION.value
            vendor_updated = True

    if decision.qualification_status != "UNQUALIFIED":
        vendor.qualification_status = decision.qualification_status

    if needs_human:
        conversation.human_controlled = True
        conversation.status = ConversationStatus.HUMAN_CONTROLLED.value
        conversation.handoff_reason = decision.reason or "AI flagged that human involvement is needed."
        if decision.intent == "request_human":
            vendor.human_handoff = True
            vendor.status = VendorStatus.HUMAN_HANDOFF.value
        if decision.intent == "request_meeting" or (vendor.qualification_status == "QUALIFIED" and decision.needs_meeting):
            if vendor.status not in (VendorStatus.MEETING_REQUESTED.value, VendorStatus.WAITING_FOR_HUMAN_LINK.value):
                vendor.status = VendorStatus.MEETING_REQUESTED.value
            conversation.status = ConversationStatus.WAITING_FOR_HUMAN_LINK.value
        await notifications.notify_human_handoff(
            db,
            vendor_id=vendor.id,
            vendor_name=vendor.contact_name or vendor.company,
            company=vendor.company,
            email=vendor.email,
            reason=conversation.handoff_reason,
            settings=settings,
        )
    else:
        conversation.status = ConversationStatus.ACTIVE.value

    if not conversation.ai_paused and decision.response:
        message = Message(
            conversation_id=conversation.id,
            vendor_id=vendor.id,
            idempotency_key=f"out-ai-{inbound.id}",
            sender=recipient_addr(vendor, settings=settings),
            recipient=inbound.sender,
            subject=subject_reply(inbound.subject or conversation.subject or ""),
            body=decision.response,
            body_html=None,
            received_at=datetime.now(UTC),
            direction=MessageDirection.OUTBOUND.value,
            origin=MessageOrigin.AI.value,
            ai_used=True,
            draft=False,
        )
        db.add(message)
        await db.flush()
        conversation.last_outbound_at = datetime.now(UTC)
        reply_id = message.id
    else:
        reply_id = None

    await db.flush()
    return {
        "intent": decision.intent,
        "qualification_status": decision.qualification_status,
        "needs_human": needs_human,
        "flagged": flagged,
        "reply_message_id": reply_id,
        "vendor_status": vendor.status,
        "conversation_status": conversation.status,
    }


_SYSTEM_PROMPT = (
    "You are the AI assistant for an AI vendor-outreach SaaS. A vendor replied to a "
    "campaign email. Classify the reply and optionally draft ONE concise, friendly reply "
    "in the same language as the vendor. "
    "NEVER invent prices, quotes, payment terms, contracts, guarantees, discounts, or "
    "hard timelines — if asked, say our team will provide precise details. "
    "Output JSON only with keys: intent (one of interested, not_interested, opt_out, "
    "ask_question, request_human, request_meeting, needs_more_info, other), "
    "qualification_status (UNQUALIFIED|QUALIFYING|QUALIFIED|NOT_QUALIFIED), "
    "needs_human (bool), needs_meeting (bool), response (string|null), reason (string)."
)


def subject_reply(subject: str) -> str:
    subject = subject.strip()
    if subject.lower().startswith(("re:", "aw:", "sv:", "fw:")):
        return subject
    return f"Re: {subject}"


def recipient_addr(vendor: Vendor, settings: Any | None = None) -> str:
    from app.config import get_settings

    settings = settings or get_settings()
    return settings.GMAIL_SENDER_EMAIL or settings.SMTP_FROM_EMAIL or settings.SMTP_USERNAME or "outreach@example.com"


def uuid4_hex() -> str:
    import uuid

    return uuid.uuid4().hex


async def pause_ai(db: AsyncSession, *, conversation: Conversation) -> None:
    """Pause AI: operator takes full control (spec: pause AI -> mark -> notify)."""
    conversation.ai_paused = True
    conversation.human_controlled = True
    conversation.status = ConversationStatus.HUMAN_CONTROLLED.value
    await db.flush()


async def resume_ai(db: AsyncSession, *, conversation: Conversation) -> None:
    conversation.ai_paused = False
    conversation.status = ConversationStatus.ACTIVE.value
    await db.flush()


async def schedule_follow_up(
    db: AsyncSession, *, conversation: Conversation, vendor: Vendor,
    campaign_days_until_follow_up: int = 3,
) -> bool:
    """Schedule the next follow-up after an AI reply (job created at send-completion)."""
    if vendor.opted_out or vendor.status in (VendorStatus.COMPLETED.value, VendorStatus.OPTED_OUT.value):
        return False
    next_step = conversation.follow_up_step + 1
    if next_step > 3:
        return False
    run_after = datetime.now(UTC) + timedelta(days=campaign_days_until_follow_up)
    job = await queue_service.enqueue_job(
        db,
        job_type="FOLLOW_UP",
        vendor_id=vendor.id,
        campaign_id=conversation.campaign_id,
        conversation_id=conversation.id,
        run_after=run_after,
        step=next_step,
        payload={"conversation_id": conversation.id, "step": next_step},
    )
    conversation.next_follow_up_at = run_after
    conversation.follow_up_step = next_step
    await db.flush()
    return True