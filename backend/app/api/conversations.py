"""Conversation endpoints: list, detail, messages, operator actions."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import CurrentUser, JsonRequest
from app.database import get_db
from app.models.conversation import Conversation
from app.models.enums import ConversationStatus, MessageDirection, MessageOrigin, VendorStatus
from app.models.message import Message
from app.models.vendor import Vendor
from app.schemas.conversation import AddNote, ConversationAction, ManualReply, MarkInterested, MarkQualified, MeetingLinkIn
from app.services import audit, conversation_service, meeting_service, optout, queue_service
from app.services.serializers import serialize_conversation, serialize_message

router = APIRouter(prefix="/conversations", tags=["conversations"])


async def _get_conversation(db: AsyncSession, conversation_id: str) -> Conversation:
    convo = await db.get(Conversation, conversation_id)
    if not convo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    return convo


async def _get_vendor_or_404(db: AsyncSession, vendor_id: str) -> Vendor:
    vendor = await db.get(Vendor, vendor_id)
    if not vendor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vendor not found")
    return vendor


@router.get("")
async def list_conversations(
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: CurrentUser,
    status_filter: str | None = Query(default=None, alias="status"),
    vendor_id: str | None = None,
    search: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict:
    stmt = (
        select(Conversation, Vendor.company, Vendor.contact_name, func.count(Message.id))
        .join(Vendor, Vendor.id == Conversation.vendor_id)
        .outerjoin(Message, Message.conversation_id == Conversation.id)
        .group_by(Conversation.id, Vendor.company, Vendor.contact_name)
        .order_by(Conversation.last_inbound_at.desc().nullslast(), Conversation.updated_at.desc())
    )
    count_stmt = select(func.count(Conversation.id))
    if status_filter:
        stmt = stmt.where(Conversation.status == status_filter)
        count_stmt = count_stmt.where(Conversation.status == status_filter)
    if vendor_id:
        stmt = stmt.where(Conversation.vendor_id == vendor_id)
        count_stmt = count_stmt.where(Conversation.vendor_id == vendor_id)
    if search:
        like = f"%{search}%"
        stmt = stmt.where(Vendor.company.ilike(like) | Conversation.subject.ilike(like))
        count_stmt = count_stmt.where(Vendor.company.ilike(like) | Conversation.subject.ilike(like))
    total = (await db.execute(count_stmt)).scalar_one()
    rows = (await db.execute(stmt.limit(limit).offset(offset))).all()
    items = []
    for convo, company, contact_name, message_count in rows:
        data = serialize_conversation(convo, message_count=message_count)
        data["company"] = company
        data["contact_name"] = contact_name
        items.append(data)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/{conversation_id}")
async def get_conversation(
    conversation_id: str, db: Annotated[AsyncSession, Depends(get_db)], _user: CurrentUser
) -> dict:
    convo = await _get_conversation(db, conversation_id)
    vendor = await _get_vendor_or_404(db, convo.vendor_id)
    messages = (
        await db.execute(
            select(Message).where(Message.conversation_id == conversation_id).order_by(Message.received_at.asc())
        )
    ).scalars().all()
    data = serialize_conversation(convo, message_count=len(messages))
    data["vendor"] = {
        "id": vendor.id,
        "company": vendor.company,
        "contact_name": vendor.contact_name,
        "email": vendor.email,
        "status": vendor.status,
        "qualification_status": vendor.qualification_status,
        "opted_out": vendor.opted_out,
        "human_handoff": vendor.human_handoff,
    }
    data["messages"] = [serialize_message(m) for m in messages]
    return data


@router.post("/{conversation_id}/messages")
async def send_manual_message(
    conversation_id: str,
    body: ManualReply,
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: CurrentUser,
    _json: JsonRequest,
) -> dict:
    """Operator sends a message (origin=HUMAN). an opt-out cancels follow-ups."""
    convo = await _get_conversation(db, conversation_id)
    vendor = await _get_vendor_or_404(db, convo.vendor_id)
    if vendor.opted_out:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Vendor opted out; do not contact")
    if optout.detect_opt_out(body.subject, body.body):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Refusing to send: message contains opt-out language")
    message = Message(
        conversation_id=conversation_id,
        vendor_id=vendor.id,
        idempotency_key=f"human-{conversation_id}-{_user.id}-{body.body[:64]}",
        sender="operator",
        recipient=vendor.email or "",
        subject=body.subject or convo.subject,
        body=body.body,
        received_at=func_now(),
        direction=MessageDirection.OUTBOUND.value,
        origin=MessageOrigin.HUMAN.value,
        ai_used=False,
        draft=False,
    )
    db.add(message)
    await db.flush()
    convo.last_outbound_at = message.received_at
    vendor.last_contacted_at = message.received_at
    await audit.audit(db, actor=_user.username, action="conversation.manual_reply", resource_type="conversation",
                      resource_id=conversation_id)
    await db.commit()
    return serialize_message(message)


@router.post("/{conversation_id}/action")
async def conversation_action(
    conversation_id: str,
    body: ConversationAction,
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: CurrentUser,
    _json: JsonRequest,
) -> dict:
    """Operator actions: pause_ai, resume_ai, take_over, return_to_ai,
    request_meeting, archive, opt_out."""
    convo = await _get_conversation(db, conversation_id)
    vendor = await _get_vendor_or_404(db, convo.vendor_id)
    action = body.action
    result = None

    if action == "pause_ai":
        await conversation_service.pause_ai(db, conversation=convo)
    elif action == "resume_ai":
        await conversation_service.resume_ai(db, conversation=convo)
    elif action == "take_over":
        convo.human_controlled = True
        convo.ai_paused = True
        convo.status = ConversationStatus.HUMAN_CONTROLLED.value
    elif action == "return_to_ai":
        convo.human_controlled = False
        convo.ai_paused = False
        convo.status = ConversationStatus.ACTIVE.value
    elif action == "request_meeting":
        meeting = await meeting_service.create_or_update_meeting_request(db, vendor=vendor, conversation=convo,
                                                                         notes=body.note)
        if vendor.status not in (VendorStatus.MEETING_REQUESTED.value, VendorStatus.WAITING_FOR_HUMAN_LINK.value,
                                 VendorStatus.MEETING_LINK_RECEIVED.value, VendorStatus.INVITATION_SENT.value):
            vendor.status = VendorStatus.MEETING_REQUESTED.value
        vendor.human_handoff = True
        convo.status = ConversationStatus.WAITING_FOR_HUMAN_LINK.value
        convo.human_controlled = True
        from app.services.serializers import serialize_meeting

        await db.flush()
        result = serialize_meeting(meeting)
    elif action == "archive":
        convo.archived = True
        convo.status = ConversationStatus.ARCHIVED.value
        result = None
    elif action == "opt_out":
        vendor.opted_out = True
        vendor.status = VendorStatus.OPTED_OUT.value
        convo.ai_paused = True
        await queue_service.cancel_jobs_for_conversation(db, conversation_id)
        result = None
    else:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Unknown action: {action}")

    await audit.audit(db, actor=_user.username, action=f"conversation.{action}", resource_type="conversation",
                      resource_id=conversation_id, details={"note": body.note})
    await db.commit()
    return {"status": "ok", "conversation": convo.status, "vendor_status": vendor.status,
            "meeting": result if action == "request_meeting" else None}


@router.post("/{conversation_id}/mark-interest")
async def mark_interest(
    conversation_id: str,
    body: MarkInterested,
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: CurrentUser,
    _json: JsonRequest,
) -> dict:
    convo = await _get_conversation(db, conversation_id)
    vendor = await _get_vendor_or_404(db, convo.vendor_id)
    from app.services import vendor_service as vs

    await vs.transition_vendor(db, vendor, VendorStatus.INTERESTED.value if body.interested else VendorStatus.NOT_INTERESTED.value, force=True)
    vendor.status = VendorStatus.INTERESTED.value if body.interested else VendorStatus.NOT_INTERESTED.value
    await audit.audit(db, actor=_user.username, action="conversation.mark_interest", resource_type="conversation",
                      resource_id=conversation_id, details={"interested": body.interested})
    await db.commit()
    return {"status": vendor.status}


@router.post("/{conversation_id}/mark-qualified")
async def mark_qualified(
    conversation_id: str,
    body: MarkQualified,
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: CurrentUser,
    _json: JsonRequest,
) -> dict:
    convo = await _get_conversation(db, conversation_id)
    vendor = await _get_vendor_or_404(db, convo.vendor_id)
    vendor.qualification_status = "QUALIFIED" if body.qualified else "NOT_QUALIFIED"
    from app.services.vendor_service import transition_vendor as _tv

    await _tv(db, vendor, VendorStatus.QUALIFIED.value if body.qualified else VendorStatus.NOT_INTERESTED.value, force=True)
    vendor.status = VendorStatus.QUALIFIED.value if body.qualified else VendorStatus.NOT_INTERESTED.value
    await audit.audit(db, actor=_user.username, action="conversation.mark_qualified", resource_type="conversation",
                      resource_id=conversation_id, details={"qualified": body.qualified})
    await db.commit()
    return {"qualification_status": vendor.qualification_status, "status": vendor.status}


@router.post("/{conversation_id}/meeting-link")
async def register_meeting_link(
    conversation_id: str,
    body: MeetingLinkIn,
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: CurrentUser,
    _json: JsonRequest,
) -> dict:
    """Operator enters a meeting link (validated) -> MEETING_LINK_RECEIVED."""
    convo = await _get_conversation(db, conversation_id)
    vendor = await _get_vendor_or_404(db, convo.vendor_id)
    meeting = await meeting_service.register_vendor_meeting_link(db, vendor=vendor, conversation=convo,
                                                                 raw_url=str(body.meeting_url))
    await audit.audit(db, actor=_user.username, action="conversation.meeting_link", resource_type="conversation",
                      resource_id=conversation_id)
    await db.commit()
    from app.services.serializers import serialize_meeting

    return {"meeting": serialize_meeting(meeting), "vendor_status": vendor.status}


@router.post("/{conversation_id}/notes")
async def add_note(
    conversation_id: str,
    body: AddNote,
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: CurrentUser,
    _json: JsonRequest,
) -> dict:
    convo = await _get_conversation(db, conversation_id)
    convo.handoff_reason = (convo.handoff_reason or "") + (f"\n[{_user.username}] {body.note}" if convo.handoff_reason else f"[{_user.username}] {body.note}")
    await audit.audit(db, actor=_user.username, action="conversation.note", resource_type="conversation",
                      resource_id=conversation_id)
    await db.commit()
    return {"ok": True}


def func_now():
    from datetime import UTC, datetime

    return datetime.now(UTC)