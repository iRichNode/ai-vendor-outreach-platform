"""Meeting endpoints: list, detail, invitation sending, lifecycle actions.

The AI never creates meetings — the operator (or a validated inbound link) does.
These endpoints expose the meeting lifecycle for the dashboard.
"""
from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import CurrentUser, JsonRequest
from app.database import get_db
from app.models.meeting import Meeting
from app.models.vendor import Vendor
from app.services import audit, meeting_service
from app.services.serializers import serialize_meeting

router = APIRouter(prefix="/meetings", tags=["meetings"])


class MeetingScheduleIn(BaseModel):
    scheduled_time: datetime | None = None


class MeetingCancelIn(BaseModel):
    reason: str = Field(default="", max_length=2000)


async def _get_meeting(db: AsyncSession, meeting_id: str) -> Meeting:
    meeting = await db.get(Meeting, meeting_id)
    if not meeting:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting not found")
    return meeting


async def _get_vendor_or_404(db: AsyncSession, vendor_id: str) -> Vendor:
    vendor = await db.get(Vendor, vendor_id)
    if not vendor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vendor not found")
    return vendor


@router.get("")
async def list_meetings(
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: CurrentUser,
    status_filter: str | None = Query(default=None, alias="status"),
    campaign_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict:
    stmt = select(Meeting, Vendor.company, Vendor.contact_name, Vendor.email).join(
        Vendor, Vendor.id == Meeting.vendor_id
    ).order_by(Meeting.created_at.desc())
    count_stmt = select(func.count(Meeting.id)).join(Vendor, Vendor.id == Meeting.vendor_id)
    if status_filter:
        stmt = stmt.where(Meeting.status == status_filter)
        count_stmt = count_stmt.where(Meeting.status == status_filter)
    if campaign_id:
        stmt = stmt.where(Meeting.campaign_id == campaign_id)
        count_stmt = count_stmt.where(Meeting.campaign_id == campaign_id)
    total = (await db.execute(count_stmt)).scalar_one()
    rows = (await db.execute(stmt.limit(limit).offset(offset))).all()
    items = []
    for meeting, company, contact_name, email in rows:
        data = serialize_meeting(meeting)
        data["vendor"] = {"company": company, "contact_name": contact_name, "email": email}
        items.append(data)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/{meeting_id}")
async def get_meeting(meeting_id: str, db: Annotated[AsyncSession, Depends(get_db)], _user: CurrentUser) -> dict:
    meeting = await _get_meeting(db, meeting_id)
    vendor = await _get_vendor_or_404(db, meeting.vendor_id)
    data = serialize_meeting(meeting)
    data["vendor"] = {
        "id": vendor.id,
        "company": vendor.company,
        "contact_name": vendor.contact_name,
        "email": vendor.email,
        "status": vendor.status,
        "meeting_status": vendor.meeting_status,
    }
    return data


@router.post("/{meeting_id}/send-invitation")
async def send_invitation(
    meeting_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: CurrentUser,
    _json: JsonRequest,
) -> dict:
    """Send the meeting invitation email to the vendor (Gmail transport)."""
    meeting = await _get_meeting(db, meeting_id)
    vendor = await _get_vendor_or_404(db, meeting.vendor_id)
    result = await meeting_service.send_invitation(db, vendor=vendor, meeting=meeting)
    if not result["ok"]:
        await audit.audit(db, actor=_user.username, action="meeting.invitation_failed", resource_type="meeting",
                          resource_id=meeting_id, details=result)
        await db.commit()
        return {"ok": False, "detail": result["detail"]}
    await audit.audit(db, actor=_user.username, action="meeting.invitation_sent", resource_type="meeting",
                      resource_id=meeting_id)
    await db.commit()
    return {"ok": True, "detail": "Invitation sent", "message_id": result.get("message_id"),
            "meeting_status": meeting.status, "vendor_status": vendor.status}


@router.post("/{meeting_id}/mark-scheduled")
async def mark_scheduled(
    meeting_id: str,
    body: MeetingScheduleIn,
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: CurrentUser,
    _json: JsonRequest,
) -> dict:
    meeting = await _get_meeting(db, meeting_id)
    vendor = await _get_vendor_or_404(db, meeting.vendor_id)
    await meeting_service.mark_meeting_scheduled(db, meeting=meeting, vendor=vendor,
                                                 scheduled_time=body.scheduled_time)
    await audit.audit(db, actor=_user.username, action="meeting.scheduled", resource_type="meeting",
                      resource_id=meeting_id)
    await db.commit()
    return serialize_meeting(meeting)


@router.post("/{meeting_id}/complete")
async def complete_meeting(
    meeting_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: CurrentUser,
    _json: JsonRequest,
) -> dict:
    meeting = await _get_meeting(db, meeting_id)
    vendor = await _get_vendor_or_404(db, meeting.vendor_id)
    await meeting_service.complete_meeting(db, meeting=meeting, vendor=vendor)
    await audit.audit(db, actor=_user.username, action="meeting.completed", resource_type="meeting",
                      resource_id=meeting_id)
    await db.commit()
    return serialize_meeting(meeting)


@router.post("/{meeting_id}/cancel")
async def cancel_meeting(
    meeting_id: str,
    body: MeetingCancelIn,
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: CurrentUser,
    _json: JsonRequest,
) -> dict:
    meeting = await _get_meeting(db, meeting_id)
    vendor = await _get_vendor_or_404(db, meeting.vendor_id)
    await meeting_service.cancel_meeting(db, meeting=meeting, vendor=vendor, reason=body.reason)
    await audit.audit(db, actor=_user.username, action="meeting.cancelled", resource_type="meeting",
                      resource_id=meeting_id, details={"reason": body.reason})
    await db.commit()
    return serialize_meeting(meeting)