"""Persistent sending queue.

The `scheduled_jobs` table is the single source of truth. Workers claim rows
atomically (dialect-aware SKIP LOCKED on PostgreSQL). A job can only complete once,
guaranteeing no duplicate emails after worker crashes or restarts.

Idempotency: every enqueue carries an `idempotency_key` with a UNIQUE constraint.
Re-enqueueing with the same key is a no-op returning the existing job.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import and_, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import JobStatus
from app.models.job import ScheduledJob

_DIALECT_SUPPORTS_SKIP_LOCKED = {"postgresql"}


def idempotency_key_for(job_type: str, vendor_id: str | None, campaign_id: str | None = None,
                        conversation_id: str | None = None, step: int | None = None,
                        suffix: str | None = None) -> str:
    parts = [job_type, vendor_id or "-", campaign_id or "-", conversation_id or "-", str(step or "-")]
    if suffix:
        parts.append(suffix)
    return "|".join(parts)


async def enqueue_job(
    db: AsyncSession,
    *,
    job_type: str,
    vendor_id: str,
    campaign_id: str | None = None,
    conversation_id: str | None = None,
    run_after: datetime,
    payload: dict[str, Any] | None = None,
    idem_key: str | None = None,
    max_attempts: int = 6,
    step: int | None = None,
    status: str = JobStatus.PENDING.value,
) -> ScheduledJob:
    """Create a job (idempotent by idem_key)."""
    key = idem_key or idempotency_key_for(job_type, vendor_id, campaign_id, conversation_id, step)
    if key:
        existing = (
            await db.execute(
                select(ScheduledJob).where(
                    and_(ScheduledJob.idempotency_key == key, ScheduledJob.status.notin_(["COMPLETED", "CANCELLED"]))
                )
            )
        ).scalars().first()
        if existing:
            return existing
    job = ScheduledJob(
        job_type=job_type,
        vendor_id=vendor_id,
        campaign_id=campaign_id,
        conversation_id=conversation_id,
        idempotency_key=key,
        payload=payload or {},
        run_after=run_after,
        status=status,
        max_attempts=max_attempts,
        step=step,
    )
    db.add(job)
    await db.flush()
    return job


async def count_pending_for(db: AsyncSession, vendor_id: str | None = None, campaign_id: str | None = None,
                            job_type: str | None = None) -> int:
    stmt = select(func.count(ScheduledJob.id)).where(ScheduledJob.status == JobStatus.PENDING.value)
    if vendor_id:
        stmt = stmt.where(ScheduledJob.vendor_id == vendor_id)
    if campaign_id:
        stmt = stmt.where(ScheduledJob.campaign_id == campaign_id)
    if job_type:
        stmt = stmt.where(ScheduledJob.job_type == job_type)
    return (await db.execute(stmt)).scalar_one()


async def cancel_jobs_for_conversation(db: AsyncSession, conversation_id: str, *,
                                       exclude_types: set[str] | None = None) -> int:
    stmt = (
        update(ScheduledJob)
        .where(
            ScheduledJob.conversation_id == conversation_id,
            ScheduledJob.status.in_([JobStatus.PENDING.value, JobStatus.PAUSED.value]),
        )
        .values(status=JobStatus.CANCELLED.value)
    )
    if exclude_types:
        stmt = stmt.where(ScheduledJob.job_type.notin_(list(exclude_types)))
    result = await db.execute(stmt)
    return result.rowcount or 0


async def cancel_jobs_for_vendor(db: AsyncSession, vendor_id: str, *, exclude_types: set[str] | None = None) -> int:
    stmt = (
        update(ScheduledJob)
        .where(
            ScheduledJob.vendor_id == vendor_id,
            ScheduledJob.status.in_([JobStatus.PENDING.value, JobStatus.PAUSED.value]),
        )
        .values(status=JobStatus.CANCELLED.value)
    )
    if exclude_types:
        stmt = stmt.where(ScheduledJob.job_type.notin_(list(exclude_types)))
    result = await db.execute(stmt)
    return result.rowcount or 0


async def cancel_jobs_for_campaign(db: AsyncSession, campaign_id: str) -> int:
    result = await db.execute(
        update(ScheduledJob)
        .where(
            ScheduledJob.campaign_id == campaign_id,
            ScheduledJob.status.in_([JobStatus.PENDING.value, JobStatus.PAUSED.value]),
        )
        .values(status=JobStatus.CANCELLED.value)
    )
    return result.rowcount or 0


async def set_paused_all_for_campaign(db: AsyncSession, campaign_id: str) -> int:
    """Pause all pending jobs for a campaign (operator pause)."""
    result = await db.execute(
        update(ScheduledJob)
        .where(
            ScheduledJob.campaign_id == campaign_id,
            ScheduledJob.status.in_([JobStatus.PENDING.value, JobStatus.CLAIMED.value]),
        )
        .values(status=JobStatus.PAUSED.value)
    )
    return result.rowcount or 0


async def resume_all_for_campaign(db: AsyncSession, campaign_id: str) -> int:
    result = await db.execute(
        update(ScheduledJob)
        .where(ScheduledJob.campaign_id == campaign_id, ScheduledJob.status == JobStatus.PAUSED.value)
        .values(status=JobStatus.PENDING.value, last_error=None)
    )
    return result.rowcount or 0


async def set_paused(db: AsyncSession, job_id: str, paused: bool) -> bool:
    target = JobStatus.PAUSED.value if paused else JobStatus.PENDING.value
    result = await db.execute(update(ScheduledJob).where(ScheduledJob.id == job_id).values(status=target))
    return bool(result.rowcount)


async def reschedule_job(db: AsyncSession, job_id: str, run_after: datetime, max_attempts: int | None = None) -> bool:
    values: dict[str, Any] = {"run_after": run_after, "status": JobStatus.PENDING.value, "last_error": None}
    if max_attempts:
        values["max_attempts"] = max_attempts
    result = await db.execute(update(ScheduledJob).where(ScheduledJob.id == job_id).values(**values))
    return bool(result.rowcount)


async def _dialect_name(db: AsyncSession) -> str:
    try:
        return db.get_bind().dialect.name
    except Exception:  # noqa: BLE001
        return "sqlite"


async def claim_jobs(db: AsyncSession, limit: int = 20, *, stale_after_seconds: int = 300) -> list[ScheduledJob]:
    """Atomically claim up to `limit` due jobs.

    On PostgreSQL the canonical CTE + FOR UPDATE SKIP LOCKED pattern is used so
    concurrent workers never double-claim. Other dialects fall back to a guarded
    single-statement claim (adequate for single-worker tests/demo).
    """
    now = datetime.now(UTC)
    claim_uuid = uuid.uuid4().hex

    # 1) reclaim stuck CLAIMED jobs
    await db.execute(
        update(ScheduledJob)
        .where(
            ScheduledJob.status == JobStatus.CLAIMED.value,
            ScheduledJob.claimed_at < now - timedelta(seconds=stale_after_seconds),
        )
        .values(
            status=JobStatus.PENDING.value,
            claim_uuid=None,
            claimed_at=None,
            attempts=ScheduledJob.attempts + 1,
        )
    )

    # 2) claim due jobs
    dialect = await _dialect_name(db)
    base_where = and_(
        ScheduledJob.status == JobStatus.PENDING.value,
        ScheduledJob.run_after <= now,
    )
    values = {
        "status": JobStatus.CLAIMED.value,
        "claim_uuid": claim_uuid,
        "claimed_at": now,
        "started_at": func.coalesce(ScheduledJob.started_at, now),
    }

    if dialect in _DIALECT_SUPPORTS_SKIP_LOCKED:
        due = (
            select(ScheduledJob.id)
            .where(base_where)
            .order_by(ScheduledJob.run_after.asc(), ScheduledJob.created_at.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
            .cte("due_jobs")
        )
        stmt = (
            update(ScheduledJob)
            .where(ScheduledJob.id.in_(select(due.c.id)))
            .values(**values)
            .returning(ScheduledJob)
        )
    else:
        inner = (
            select(ScheduledJob.id).where(base_where)
            .order_by(ScheduledJob.run_after.asc(), ScheduledJob.created_at.asc())
            .limit(limit)
        )
        stmt = (
            update(ScheduledJob)
            .where(ScheduledJob.id.in_(inner))
            .values(**values)
            .returning(ScheduledJob)
        )

    rows = (await db.execute(stmt)).scalars().all()
    await db.commit()
    return list(rows)


def _backoff(attempt: int, base_seconds: int = 20, factor: float = 2.0, cap_seconds: int = 3600) -> timedelta:
    seconds = min(cap_seconds, base_seconds * (factor ** max(0, attempt - 1)))
    return timedelta(seconds=seconds)


async def complete_job(db: AsyncSession, job: ScheduledJob, *, error: str | None = None) -> None:
    """Mark a claimed job completed, or schedule a retry with exponential backoff."""
    if error:
        job.last_error = error
        job.attempts += 1
        if job.attempts >= job.max_attempts:
            job.status = JobStatus.FAILED.value
        else:
            job.status = JobStatus.PENDING.value
            job.run_after = datetime.now(UTC) + _backoff(job.attempts)
        job.claim_uuid = None
        job.claimed_at = None
    else:
        job.status = JobStatus.COMPLETED.value
        job.completed_at = datetime.now(UTC)
        job.claim_uuid = None
        job.claimed_at = None
    await db.flush()


async def list_jobs(
    db: AsyncSession,
    *,
    status: str | None = None,
    job_type: str | None = None,
    vendor_id: str | None = None,
    campaign_id: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[ScheduledJob]:
    stmt = select(ScheduledJob).order_by(ScheduledJob.run_after.asc())
    if status:
        stmt = stmt.where(ScheduledJob.status == status)
    if job_type:
        stmt = stmt.where(ScheduledJob.job_type == job_type)
    if vendor_id:
        stmt = stmt.where(ScheduledJob.vendor_id == vendor_id)
    if campaign_id:
        stmt = stmt.where(ScheduledJob.campaign_id == campaign_id)
    return list((await db.execute(stmt.limit(limit).offset(offset))).scalars().all())


GLOBAL_PAUSE_KEY = "general.outreach_paused"


async def is_global_paused(db: AsyncSession) -> bool:
    """True when PAUSE ALL is active (spec: queued jobs remain stored)."""
    from app.models.settings import AppSetting

    row = (
        await db.execute(select(AppSetting).where(AppSetting.key == GLOBAL_PAUSE_KEY))
    ).scalars().first()
    if row is None:
        return False
    return str(row.value).strip().lower() in {"1", "true", "yes", "on"}


async def set_global_paused(db: AsyncSession, paused: bool) -> None:
    from app.models.settings import AppSetting

    row = (
        await db.execute(select(AppSetting).where(AppSetting.key == GLOBAL_PAUSE_KEY))
    ).scalars().first()
    if row is None:
        row = AppSetting(key=GLOBAL_PAUSE_KEY, value="true" if paused else "false",
                         value_type="bool", section="general")
        db.add(row)
    else:
        row.value = "true" if paused else "false"
        row.value_type = "bool"
    await db.flush()


async def purge_completed(db: AsyncSession, older_than_days: int = 30) -> int:
    cutoff = datetime.now(UTC) - timedelta(days=older_than_days)
    result = await db.execute(
        delete(ScheduledJob).where(
            ScheduledJob.status.in_([JobStatus.COMPLETED.value, JobStatus.CANCELLED.value]),
            ScheduledJob.updated_at < cutoff,
        )
    )
    return result.rowcount or 0