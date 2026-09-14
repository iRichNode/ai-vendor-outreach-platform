"""Dashboard aggregate endpoint: quick numbers for the landing page."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import CurrentUser
from app.database import get_db
from app.models.campaign import Campaign
from app.models.conversation import Conversation
from app.models.job import ScheduledJob
from app.models.meeting import Meeting
from app.models.notification import Notification
from app.services.analytics import dashboard_metrics
from app.services import queue_service

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("")
async def dashboard(
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: CurrentUser,
) -> dict:
    metrics = await dashboard_metrics(db)
    active_campaigns = (
        await db.execute(select(func.count(Campaign.id)).where(Campaign.status.in_(["ACTIVE", "PAUSED"])))
    ).scalar_one()
    active_conversations = (
        await db.execute(
            select(func.count(Conversation.id)).where(
                Conversation.status.in_(["ACTIVE", "HUMAN_CONTROLLED", "HUMAN_HANDOFF",
                                         "WAITING_FOR_HUMAN_LINK", "NEEDS_REVIEW"])
            )
        )
    ).scalar_one()
    pending_jobs = (
        await db.execute(select(func.count(ScheduledJob.id)).where(ScheduledJob.status == "PENDING"))
    ).scalar_one()
    unread_notifications = (
        await db.execute(select(func.count(Notification.id)).where(Notification.read.is_(False)))
    ).scalar_one()
    meetings_pending = (
        await db.execute(
            select(func.count(Meeting.id)).where(Meeting.status.in_(["REQUESTED", "WAITING_FOR_LINK", "LINK_RECEIVED"]))
        )
    ).scalar_one()
    return {
        "metrics": metrics,
        "counts": {
            "active_campaigns": active_campaigns,
            "active_conversations": active_conversations,
            "pending_jobs": pending_jobs,
            "unread_notifications": unread_notifications,
            "meetings_pending": meetings_pending,
        },
        "global_paused": await queue_service.is_global_paused(db),
    }