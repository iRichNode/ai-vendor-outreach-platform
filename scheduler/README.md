# Scheduler service

A lightweight maintenance loop (the role a Celery-beat process would play):

1. **Reclaims stuck claims** — `CLAIMED` jobs older than
   `JOB_STALE_AFTER_SECONDS` (workers hard-killed mid-job) are reset to
   `PENDING` for a healthy worker to retry.
2. **Prunes terminal history** — `COMPLETED` / `FAILED` / `CANCELLED` jobs
   older than `JOB_RETENTION_DAYS` (default 30) are deleted.
3. **Logs queue totals** every cycle for observability.

Implementation: `backend/app/workers/scheduler.py`.

Run via Docker:

```sh
docker compose up -d --build scheduler
```

Local (no Docker):

```sh
cd backend
DATABASE_URL=... REDIS_URL=... python -m app.workers.scheduler
```

Tunables: `SCHEDULER_INTERVAL_SECONDS` (default 300), `JOB_RETENTION_DAYS`.