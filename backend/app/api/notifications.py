"""Notification inbox endpoints."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import CurrentUser, JsonRequest
from app.database import get_db
from app.models.notification import Notification
from app.schemas.misc import NotificationReadPatch
from app.services.serializers import serialize_notification

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("")
async def list_notifications(
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: CurrentUser,
    unread_only: bool = False,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict:
    stmt = select(Notification).order_by(Notification.event_time.desc())
    count_stmt = select(func.count(Notification.id))
    if unread_only:
        stmt = stmt.where(Notification.read.is_(False))
        count_stmt = count_stmt.where(Notification.read.is_(False))
    total = (await db.execute(count_stmt)).scalar_one()
    rows = (await db.execute(stmt.limit(limit).offset(offset))).scalars().all()
    return {"items": [serialize_notification(n) for n in rows], "total": total,
            "limit": limit, "offset": offset, "unread_only": unread_only}


@router.get("/unread-count")
async def unread_count(db: Annotated[AsyncSession, Depends(get_db)], _user: CurrentUser) -> dict:
    unread = (
        await db.execute(select(func.count(Notification.id)).where(Notification.read.is_(False)))
    ).scalar_one()
    return {"unread": unread}


@router.post("/read")
async def mark_read(
    body: NotificationReadPatch,
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: CurrentUser,
    _json: JsonRequest,
) -> dict:
    if body.all:
        result = await db.execute(update(Notification).values(read=True))
    elif body.ids:
        result = await db.execute(
            update(Notification).where(Notification.id.in_(body.ids)).values(read=True)
        )
    else:
        return {"updated": 0}
    updated = result.rowcount or 0
    await db.commit()
    return {"updated": updated}


@router.post("/clear")
async def clear_read(
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: CurrentUser,
    _json: JsonRequest,
) -> dict:
    result = await db.execute(delete(Notification).where(Notification.read.is_(True)))
    removed = result.rowcount or 0
    await db.commit()
    return {"removed": removed}