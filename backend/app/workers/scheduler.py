"""Maintenance scheduler (Celery-beat-style service).

Runs periodic, idempotent maintenance against the database-backed job queue:

1. **Reclaim stuck claims** — any job left in ``CLAIMED`` state for longer than
   ``JOB_STALE_AFTER_SECONDS`` (e.g. a worker that was hard-killed mid-job) is
   reset to ``PENDING`` so a healthy worker can claim and dispatch it again.
   The queue's ``claim_jobs`` performs the same reclaim opportunistically; this
   service guarantees it also happens when no worker is running.

2. **Prune terminal history** — ``COMPLETED`` / ``FAILED`` / ``CANCELLED`` jobs
   older than ``JOB_RETENTION_DAYS`` (default 30) are deleted so the queue table
   does not grow without bound.

3. **Observability** — logs queue totals every cycle for dashboards/log central.

Run:
    python -m app.workers.scheduler
"""
from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select, update

from app.config import get_settings
from app.database import create_engine_and_session
from app.models.enums import JobStatus
from app.models.job import ScheduledJob

logger = logging.getLogger("app.scheduler")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


async def reclaim_stuck_jobs(db, stale_after_seconds: int) -> int:
    """Reset CLAIMED jobs older than the staleness window back to PENDING."""
    cutoff = datetime.now(UTC) - timedelta(seconds=stale_after_seconds)
    result = await db.execute(
        update(ScheduledJob)
        .where(
            ScheduledJob.status == JobStatus.CLAIMED.value,
            ScheduledJob.claimed_at < cutoff,
        )
        .values(
            status=JobStatus.PENDING.value,
            claim_uuid=None,
            claimed_at=None,
            attempts=ScheduledJob.attempts + 1,
        )
    )
    return result.rowcount or 0


async def prune_terminal_jobs(db, retention_days: int) -> int:
    """Delete COMPLETED/FAILED/CANCELLED jobs older than the retention window."""
    cutoff = datetime.now(UTC) - timedelta(days=retention_days)
    result = await db.execute(
        delete(ScheduledJob).where(
            ScheduledJob.status.in_(
                [JobStatus.COMPLETED.value, JobStatus.FAILED.value, JobStatus.CANCELLED.value]
            ),
            ScheduledJob.claimed_at < cutoff,
        )
    )
    return result.rowcount or 0


async def queue_totals(db) -> dict[str, int]:
    """Per-status job counts for observability."""
    rows = (
        await db.execute(
            select(ScheduledJob.status, func.count(ScheduledJob.id)).group_by(ScheduledJob.status)
        )
    ).all()
    return {status: count for status, count in rows}


async def run_once(settings) -> None:
    _, session_factory = create_engine_and_session()
    async with session_factory() as db:
        reclaimed = await reclaim_stuck_jobs(db, settings.JOB_STALE_AFTER_SECONDS)
        pruned = await prune_terminal_jobs(db, settings.JOB_RETENTION_DAYS)
        totals = await queue_totals(db)
        await db.commit()
    logger.info(
        "scheduler_cycle reclaimed=%d pruned=%d queue=%s",
        reclaimed,
        pruned,
        totals,
    )


async def main() -> None:
    settings = get_settings()
    interval = settings.SCHEDULER_INTERVAL_SECONDS or 300
    logger.info("scheduler started interval_seconds=%s", interval)
    while True:
        try:
            await run_once(settings)
        except Exception as exc:  # noqa: BLE001 - scheduler must survive cycle failures
            logger.exception("scheduler_cycle_error detail=%s", str(exc))
        await asyncio.sleep(interval)


if __name__ == "__main__":
    asyncio.run(main())