# Worker service

The worker is a long-running async process that claims **due jobs** from the
PostgreSQL-backed queue (atomic `SKIP LOCKED` claim) and dispatches them through
the same services the API uses: Gmail transport, AI reply engine, meeting
invitations and follow-up chaining.

It runs as its own container in `docker-compose.yml` using the backend image:

```sh
docker compose up -d --build worker
```

Local (no Docker):

```sh
cd backend
DATABASE_URL=... REDIS_URL=... python -m app.workers.worker
```

Why there is no Celery: the queue lives in PostgreSQL (`scheduled_jobs` table)
with an idempotency-key constraint, so a worker restart can never duplicate
mail and no extra broker coordination is needed. The `scheduler` service
handles the maintenance tasks a Celery beat process would otherwise do.