"""Analytics endpoints: funnel metrics, dashboard counters, per-campaign summary.

Every number is computed from real rows — nothing is fabricated or randomized.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import CurrentUser
from app.database import get_db
from app.models.campaign import Campaign, CampaignVendor
from app.models.conversation import Conversation
from app.models.enums import MessageDirection, VendorStatus
from app.models.message import Message
from app.models.vendor import Vendor
from app.services.analytics import dashboard_metrics, funnel_series

router = APIRouter(prefix="/analytics", tags=["analytics"])

# Statuses that are at least as far as "interested" in the funnel.
_INTERESTED_OR_FURTHER = [
    VendorStatus.INTERESTED, VendorStatus.QUALIFYING, VendorStatus.QUALIFIED,
    VendorStatus.MEETING_REQUESTED, VendorStatus.WAITING_FOR_HUMAN_LINK,
    VendorStatus.MEETING_LINK_RECEIVED, VendorStatus.INVITATION_SENT,
    VendorStatus.MEETING_SCHEDULED, VendorStatus.HUMAN_HANDOFF, VendorStatus.COMPLETED,
]
_QUALIFIED_OR_FURTHER = [
    VendorStatus.QUALIFIED, VendorStatus.MEETING_REQUESTED, VendorStatus.WAITING_FOR_HUMAN_LINK,
    VendorStatus.MEETING_LINK_RECEIVED, VendorStatus.INVITATION_SENT,
    VendorStatus.MEETING_SCHEDULED, VendorStatus.HUMAN_HANDOFF, VendorStatus.COMPLETED,
]


@router.get("/dashboard")
async def analytics_dashboard(
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: CurrentUser,
    campaign_id: str | None = None,
) -> dict:
    metrics = await dashboard_metrics(db, campaign_id=campaign_id)
    active_campaigns = (
        await db.execute(
            select(func.count(Campaign.id)).where(Campaign.status.in_(["ACTIVE", "PAUSED"]))
        )
    ).scalar_one()
    metrics["active_campaigns"] = active_campaigns
    return metrics


@router.get("/funnel")
async def analytics_funnel(
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: CurrentUser,
    campaign_id: str | None = None,
) -> dict:
    return {"series": await funnel_series(db, campaign_id=campaign_id)}


@router.get("/summary")
async def analytics_summary(
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: CurrentUser,
) -> dict:
    """Emails sent, replies, reply rate, interested, qualified, meetings, opt-outs,
    bounces — overall and per campaign (real rows only)."""
    overall = await _compute_summary(db, campaign_id=None)
    campaigns = (await db.execute(select(Campaign).order_by(Campaign.created_at.desc()))).scalars().all()
    per_campaign = []
    for campaign in campaigns:
        data = await _compute_summary(db, campaign_id=campaign.id)
        data["campaign_id"] = campaign.id
        data["campaign_name"] = campaign.name
        data["campaign_status"] = campaign.status
        per_campaign.append(data)
    return {"overall": overall, "campaigns": per_campaign}


async def _compute_summary(db: AsyncSession, *, campaign_id: str | None) -> dict:
    # Messages
    sent_stmt = select(func.count(Message.id)).where(Message.direction == MessageDirection.OUTBOUND.value)
    reply_stmt = select(func.count(Message.id)).where(Message.direction == MessageDirection.INBOUND.value)
    if campaign_id:
        sent_stmt = sent_stmt.join(Conversation, Conversation.id == Message.conversation_id).where(
            Conversation.campaign_id == campaign_id)
        reply_stmt = reply_stmt.join(Conversation, Conversation.id == Message.conversation_id).where(
            Conversation.campaign_id == campaign_id)
    emails_sent = (await db.execute(sent_stmt)).scalar_one()
    replies = (await db.execute(reply_stmt)).scalar_one()

    # Vendors
    async def _status_count(statuses: list[VendorStatus]) -> int:
        query = select(func.count(Vendor.id)).where(Vendor.status.in_([s.value for s in statuses]))
        if campaign_id:
            query = query.join(CampaignVendor, CampaignVendor.vendor_id == Vendor.id).where(
                CampaignVendor.campaign_id == campaign_id
            )
        return (await db.execute(query)).scalar_one()

    async def _flag_count(flag: str) -> int:
        column = getattr(Vendor, flag)
        query = select(func.count(Vendor.id)).where(column.is_(True))
        if campaign_id:
            query = query.join(CampaignVendor, CampaignVendor.vendor_id == Vendor.id).where(
                CampaignVendor.campaign_id == campaign_id
            )
        return (await db.execute(query)).scalar_one()

    from app.models.meeting import Meeting

    meeting_stmt = select(func.count(Meeting.id))
    if campaign_id:
        meeting_stmt = meeting_stmt.where(Meeting.campaign_id == campaign_id)
    meetings_requested = (await db.execute(meeting_stmt)).scalar_one()

    scheduled_stmt = select(func.count(Meeting.id)).where(
        Meeting.status.in_(["SCHEDULED", "COMPLETED"])
    )
    if campaign_id:
        scheduled_stmt = scheduled_stmt.where(Meeting.campaign_id == campaign_id)
    meetings_scheduled = (await db.execute(scheduled_stmt)).scalar_one()

    return {
        "emails_sent": emails_sent,
        "replies": replies,
        "reply_rate": round(replies / emails_sent, 4) if emails_sent else 0.0,
        "interested": await _status_count(_INTERESTED_OR_FURTHER),
        "qualified": await _status_count(_QUALIFIED_OR_FURTHER),
        "meetings_requested": meetings_requested,
        "meetings_scheduled": meetings_scheduled,
        "opted_out": await _flag_count("opted_out"),
        "bounced": await _flag_count("bounced"),
    }