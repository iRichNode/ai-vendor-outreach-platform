"""Dashboard analytics built from the database. No fabricated stats."""
from __future__ import annotations

from collections import Counter

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.campaign import CampaignVendor
from app.models.enums import VendorStatus
from app.models.vendor import Vendor

# Funnel metrics the dashboard shows (qualified vendors, meetings requested/
# scheduled, waiting for human, opt-outs, bounces) all come from real rows.

FUNNEL_STATUSES = [
    VendorStatus.NEW,
    VendorStatus.RESEARCHED,
    VendorStatus.READY_TO_CONTACT,
    VendorStatus.CONTACTED,
    VendorStatus.REPLIED,
    VendorStatus.AI_CONVERSATION,
    VendorStatus.INTERESTED,
    VendorStatus.QUALIFYING,
    VendorStatus.QUALIFIED,
    VendorStatus.MEETING_REQUESTED,
    VendorStatus.WAITING_FOR_HUMAN_LINK,
    VendorStatus.MEETING_LINK_RECEIVED,
    VendorStatus.INVITATION_SENT,
    VendorStatus.MEETING_SCHEDULED,
    VendorStatus.HUMAN_HANDOFF,
    VendorStatus.COMPLETED,
    VendorStatus.NOT_INTERESTED,
    VendorStatus.OPTED_OUT,
    VendorStatus.BOUNCED,
]


async def dashboard_metrics(session: AsyncSession, *, campaign_id: str | None = None) -> dict:
    """Compute dashboard metrics. Every number is counted from real rows."""
    query = select(Vendor.status, func.count(Vendor.id)).group_by(Vendor.status).order_by(Vendor.status)
    if campaign_id:
        query = query.join(CampaignVendor, CampaignVendor.vendor_id == Vendor.id).where(
            CampaignVendor.campaign_id == campaign_id
        )
    rows = (await session.execute(query)).all()
    counts = Counter({VendorStatus(status): count for status, count in rows})

    metrics = {
        "total_vendors": sum(counts.values()),
        "new": counts[VendorStatus.NEW],
        "researched": counts[VendorStatus.RESEARCHED],
        "ready_to_contact": counts[VendorStatus.READY_TO_CONTACT],
        "contacted": counts[VendorStatus.CONTACTED],
        "replied": counts[VendorStatus.REPLIED],
        "ai_conversation": counts[VendorStatus.AI_CONVERSATION],
        "interested": counts[VendorStatus.INTERESTED],
        "qualifying": counts[VendorStatus.QUALIFYING],
        "qualified": counts[VendorStatus.QUALIFIED],
        "meeting_requested": counts[VendorStatus.MEETING_REQUESTED],
        "waiting_for_human": counts[VendorStatus.WAITING_FOR_HUMAN_LINK],
        "meeting_link_received": counts[VendorStatus.MEETING_LINK_RECEIVED],
        "invitation_sent": counts[VendorStatus.INVITATION_SENT],
        "meetings_scheduled": counts[VendorStatus.MEETING_SCHEDULED],
        "human_handoff": counts[VendorStatus.HUMAN_HANDOFF],
        "completed": counts[VendorStatus.COMPLETED],
        "not_interested": counts[VendorStatus.NOT_INTERESTED],
        "opted_out": counts[VendorStatus.OPTED_OUT],
        "bounced": counts[VendorStatus.BOUNCED],
    }
    # Funnel bucket values, derived by simple addition of real counts.
    metrics["in_funnel"] = sum(
        counts[s]
        for s in (
            VendorStatus.CONTACTED,
            VendorStatus.REPLIED,
            VendorStatus.AI_CONVERSATION,
            VendorStatus.INTERESTED,
            VendorStatus.QUALIFYING,
            VendorStatus.QUALIFIED,
            VendorStatus.MEETING_REQUESTED,
            VendorStatus.WAITING_FOR_HUMAN_LINK,
            VendorStatus.MEETING_LINK_RECEIVED,
            VendorStatus.INVITATION_SENT,
            VendorStatus.MEETING_SCHEDULED,
            VendorStatus.HUMAN_HANDOFF,
        )
    )
    return metrics


async def funnel_series(session: AsyncSession, *, campaign_id: str | None = None) -> list[dict]:
    """Per-status funnel bars for the analytics page."""
    metrics = await dashboard_metrics(session, campaign_id=campaign_id)
    labels = {
        "total_vendors": "All vendors",
        "in_funnel": "In funnel",
        "qualified": "Qualified",
        "meeting_requested": "Meetings requested",
        "meetings_scheduled": "Meetings scheduled",
        "waiting_for_human": "Waiting for human",
        "opted_out": "Opted out",
        "bounced": "Bounced",
    }
    return [
        {"key": key, "label": label, "value": metrics.get(key, 0)}
        for key, label in labels.items()
        if key in metrics
    ]