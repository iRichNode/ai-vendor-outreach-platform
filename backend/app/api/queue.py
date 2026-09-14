"""Queue dashboard endpoints: inspect, pause/resume/cancel/reschedule/retry.

PAUSE ALL (global pause) is stored as an AppSetting so the worker honours it and
jobs are never lost — they simply stop being claimed while paused.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import CurrentUser, JsonRequest
from app.database import get_db
from app.models.enums import JobStatus
from app.models.job import ScheduledJob
from app.schemas.misc import GlobalPausePatch, RescheduleJob
from app.services import audit, queue_service
from app.services.serializers import serialize_job

router = APIRouter(prefix="/queue", tags=["queue"])


async def _get_job(db: AsyncSession, job_id: str) -> ScheduledJob:
    job = await db.get(ScheduledJob, job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return job


@router.get("")
async def list_jobs(
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: CurrentUser,
    status_filter: str | None = Query(default=None, alias="status"),
    job_type: str | None = None,
    campaign_id: str | None = None,
    vendor_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict:
    stmt = select(ScheduledJob).order_by(ScheduledJob.run_after.asc())
    count_stmt = select(func.count(ScheduledJob.id))
    if status_filter:
        stmt = stmt.where(ScheduledJob.status == status_filter)
        count_stmt = count_stmt.where(ScheduledJob.status == status_filter)
    if job_type:
        stmt = stmt.where(ScheduledJob.job_type == job_type)
        count_stmt = count_stmt.where(ScheduledJob.job_type == job_type)
    if campaign_id:
        stmt = stmt.where(ScheduledJob.campaign_id == campaign_id)
        count_stmt = count_stmt.where(ScheduledJob.campaign_id == campaign_id)
    if vendor_id:
        stmt = stmt.where(ScheduledJob.vendor_id == vendor_id)
        count_stmt = count_stmt.where(ScheduledJob.vendor_id == vendor_id)
    total = (await db.execute(count_stmt)).scalar_one()
    jobs = (await db.execute(stmt.limit(limit).offset(offset))).scalars().all()
    return {"items": [serialize_job(j) for j in jobs], "total": total, "limit": limit, "offset": offset}


@router.get("/stats")
async def queue_stats(
    db: Annotated[AsyncSession, Depends(get_db)], _user: CurrentUser
) -> dict:
    rows = (
        await db.execute(select(ScheduledJob.status, func.count(ScheduledJob.id)).group_by(ScheduledJob.status))
    ).all()
    counts = {s: c for s, c in rows}
    total = sum(counts.values())
    return {
        "total": total,
        "pending": counts.get(JobStatus.PENDING.value, 0),
        "claimed": counts.get(JobStatus.CLAIMED.value, 0),
        "paused": counts.get(JobStatus.PAUSED.value, 0),
        "failed": counts.get(JobStatus.FAILED.value, 0),
        "cancelled": counts.get(JobStatus.CANCELLED.value, 0),
        "completed": counts.get(JobStatus.COMPLETED.value, 0),
        "global_paused": await queue_service.is_global_paused(db),
    }


@router.get("/global-pause")
async def global_pause_status(db: Annotated[AsyncSession, Depends(get_db)], _user: CurrentUser) -> dict:
    return {"paused": await queue_service.is_global_paused(db)}


@router.post("/global-pause")
async def set_global_pause(
    body: GlobalPausePatch,
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: CurrentUser,
    _json: JsonRequest,
) -> dict:
    await queue_service.set_global_paused(db, body.paused)
    await audit.audit(db, actor=_user.username, action="queue.global_pause" if body.paused else "queue.global_resume",
                      resource_type="system")
    await db.commit()
    return {"paused": body.paused}


@router.post("/purge")
async def purge_queue(
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: CurrentUser,
    _json: JsonRequest,
    older_than_days: int = Query(default=30, ge=0, le=365),
) -> dict:
    removed = await queue_service.purge_completed(db, older_than_days=older_than_days)
    await audit.audit(db, actor=_user.username, action="queue.purge", resource_type="system",
                      details={"older_than_days": older_than_days, "removed": removed})
    await db.commit()
    return {"removed": removed}


@router.post("/{job_id}/pause")
async def pause_job(
    job_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: CurrentUser,
    _json: JsonRequest,
) -> dict:
    job = await _get_job(db, job_id)
    if job.status not in (JobStatus.PENDING.value, JobStatus.CLAIMED.value):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Cannot pause job in state {job.status}")
    await queue_service.set_paused(db, job_id, paused=True)
    await audit.audit(db, actor=_user.username, action="queue.pause", resource_type="scheduled_job", resource_id=job_id)
    await db.commit()
    job = await _get_job(db, job_id)
    return serialize_job(job)


@router.post("/{job_id}/resume")
async def resume_job(
    job_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: CurrentUser,
    _json: JsonRequest,
) -> dict:
    job = await _get_job(db, job_id)
    if job.status != JobStatus.PAUSED.value:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only paused jobs can be resumed")
    await queue_service.set_paused(db, job_id, paused=False)
    await audit.audit(db, actor=_user.username, action="queue.resume", resource_type="scheduled_job", resource_id=job_id)
    await db.commit()
    job = await _get_job(db, job_id)
    return serialize_job(job)


@router.post("/{job_id}/cancel")
async def cancel_job(
    job_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: CurrentUser,
    _json: JsonRequest,
) -> dict:
    job = await _get_job(db, job_id)
    if job.status not in (JobStatus.PENDING.value, JobStatus.PAUSED.value):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Cannot cancel job in state {job.status}")
    from sqlalchemy import update

    await db.execute(update(ScheduledJob).where(ScheduledJob.id == job_id).values(status=JobStatus.CANCELLED.value))
    await audit.audit(db, actor=_user.username, action="queue.cancel", resource_type="scheduled_job", resource_id=job_id)
    await db.commit()
    job = await _get_job(db, job_id)
    return serialize_job(job)


@router.post("/{job_id}/retry")
async def retry_job(
    job_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: CurrentUser,
    _json: JsonRequest,
) -> dict:
    job = await _get_job(db, job_id)
    if job.status not in (JobStatus.FAILED.value, JobStatus.CANCELLED.value):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only failed or cancelled jobs can be retried")
    await queue_service.reschedule_job(db, job_id, run_after=datetime.now(UTC), max_attempts=job.max_attempts)
    await audit.audit(db, actor=_user.username, action="queue.retry", resource_type="scheduled_job", resource_id=job_id)
    await db.commit()
    job = await _get_job(db, job_id)
    return serialize_job(job)


@router.post("/{job_id}/reschedule")
async def reschedule_job(
    job_id: str,
    body: RescheduleJob,
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: CurrentUser,
    _json: JsonRequest,
) -> dict:
    job = await _get_job(db, job_id)
    if job.status in (JobStatus.COMPLETED.value,):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Completed jobs cannot be rescheduled")
    try:
        run_after = datetime.fromisoformat(body.run_after.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Invalid run_after: {exc}")
    if run_after.tzinfo is None:
        run_after = run_after.replace(tzinfo=UTC)
    await queue_service.reschedule_job(db, job_id, run_after=run_after, max_attempts=body.max_attempts)
    await audit.audit(db, actor=_user.username, action="queue.reschedule", resource_type="scheduled_job",
                      resource_id=job_id, details={"reason": body.reason})
    await db.commit()
    job = await _get_job(db, job_id)
    return serialize_job(job)