# Architecture

This document describes the runtime architecture of the AI Vendor Outreach
Platform: the processes, the data model, the job queue, and the key flows.

## 1. System overview

```
                        ┌────────────────────────────────────────────┐
                        │            reverse-proxy (nginx)           │
                        │  http://host:80   /api/*  -> api:8000      │
                        │                  /*       -> frontend:3000  │
                        └────────────────────────────────────────────┘
                             │                          │
                  HTML/static/Next.js             JSON API (FastAPI)
                  frontend (Next.js 15)           api (FastAPI + SQLAlchemy async)
                        │                          │        │
                                             PostgreSQL  Redis
                                             (state)     (rate limit / integrations)
                                                        │
                                            ┌───────────┴────────────┐
                                            │ worker                │ scheduler
                                            │ (outbound dispatcher)  │ (maintenance)
                                            └────────────────────────┘
```

Seven Docker Compose services: `postgres`, `redis`, `api`, `worker`,
`scheduler`, `frontend`, `reverse-proxy`. Only the reverse proxy publishes a
port (80 by default).

## 2. Processes

### api — FastAPI application (`backend/app/main.py`)

- Serves the JSON API under `/api` (OpenAPI at `/api/docs`, schema at
  `/api/openapi.json`).
- Root-level probes: `/health` (liveness, always 200 when the process is up)
  and `/ready` (readiness – verifies PostgreSQL and Redis, returns **200** when
  healthy or **503** with a `{"status":"degraded", ...}` body on failure).
- Runs under Gunicorn with uvicorn workers in Docker (default 2 workers; tune
  with `GUNICORN_WORKERS`).
- On startup, runs Alembic migrations up to `head` (unless
  `SKIP_AUTO_MIGRATE=1`).
- In `development`/`test` environments or with `DEMO_MODE=true`, it additionally
  runs `create_all` (idempotent) so a local run needs no manual migration step.

### worker — outbound job dispatcher (`backend/app/workers/worker.py`)

- A custom asyncio loop (not Celery) that polls the database-backed queue
  (`scheduled_jobs`) every `DISPATCH_INTERVAL_SECONDS` (default 60 s).
- Claims due jobs with **dialect-aware `SELECT … FOR UPDATE SKIP LOCKED`**
  (PostgreSQL) or a fallback for SQLite, so concurrent workers never double-send.
- Executes jobs by type (send email, send follow-up, AI reply, meeting
  invitation, Telegram notification, etc.) via the same service layer the API
  uses.
- Records results back onto the job row (`status`, `attempts`, `last_error`,
  `completed_at`) and appends an audit log entry.
- **Idempotency:** jobs carry a unique `idempotency_key` (UNIQUE constraint in
  PostgreSQL). A successful job can never be enqueued twice.

### scheduler — queue maintenance (`backend/app/workers/scheduler.py`)

- Runs every `SCHEDULER_INTERVAL_SECONDS` (default 300 s):
  - **Reclaim** jobs stuck in `CLAIMED` for longer than `JOB_STALE_AFTER_SECONDS`
    (default 300) back to `PENDING`, clear their `claim_uuid`, and increment
    `attempts`.
  - **Prune** terminal jobs (`COMPLETED`/`FAILED`/`CANCELLED`) older than
    `JOB_RETENTION_DAYS` (default 30) to bound queue-table growth.
- Rationale: the queue is plain database rows, so a crashed worker leaves no
  orphaned in-memory state — this process heals it automatically.

### frontend — Next.js dashboard (`frontend/`)

- React 19 + Tailwind 4. Reads the API base URL from the
  `NEXT_PUBLIC_API_URL` build-time variable — **empty** (default) means
  "same origin as the dashboard" (call paths already include `/api`), which is
  how it is deployed behind the reverse proxy. Server-side fetches (SSR) use
  the absolute `API_INTERNAL_URL` (`http://api:8000` in compose).
- Served by `next start` in the container (port 3000).

### reverse-proxy — nginx (`infra/nginx/`)

- Terminates client connections, proxies `/api/` to the API service and
  everything else to the frontend.
- TLS termination is intentionally left commented out in
  `docker-compose.yml`; see [deployment.md](deployment.md) for the production
  HTTPS recipe.

## 3. Data model

Alembic migration `b14fd4c0615e` ("initial schema") creates 13 tables:

| Table | Purpose |
|---|---|
| `users` | Operators (hashed passwords, active flag) |
| `settings` | Key/value app settings |
| `email_accounts` | Gmail/SMTP account configuration and status |
| `oauth_credentials` | Encrypted OAuth credentials (Gmail tokens at rest) |
| `vendors` | Vendor records with status workflow |
| `campaigns` | Campaign configuration (pacing, follow-ups, business hours) |
| `campaign_vendors` | Vendors attached to a campaign (opt-out, pause state) |
| `conversations` | Threads with a vendor (AI-managed or human) |
| `messages` | Individual messages in a conversation |
| `meetings` | Meeting requests and outcomes (AI never creates meetings) |
| `scheduled_jobs` | The job queue (idempotency keys, claim state, results) |
| `notifications` | In-app notification records |
| `audit_logs` | Append-only audit trail of sensitive operations |

Relationships are enforced with real foreign keys (e.g. `scheduled_jobs.vendor_id`
references `vendors.id`) — verified by integration tests.

## 4. Key flows

### Campaign dispatch

1. The scheduler/API marks campaign-vendor pairs "due" and enqueues a
   `send_email` job with an `idempotency_key`.
2. The worker claims due jobs (SKIP LOCKED), applies pacing rules
   (`services/pacing.py`: batch size, min/max delay, daily cap, business-hours
   window, per-vendor pause/opt-out, global pause), and sends via the active
   Gmail transport (`auto | smtp | api | fake`).
3. The worker marks the job `COMPLETED`, advances the vendor/campaign state
   machine, and schedules the next follow-up if configured.

### AI conversation

1. Inbound Gmail replies are fetched by the worker and turned into
   `messages` in the vendor's `conversation`.
2. If the conversation is AI-managed and within sending hours, the AI
   (`services/ai.py`, OpenAI-compatible endpoint — default OpenRouter) classifies
   intent: interested / not interested / opt-out / meeting request / needs human.
3. Opt-outs are honored immediately; meeting requests are escalated to the
   operator — the AI never creates meetings or calendar events.
4. An operator can take over any conversation at any time.

### Meeting flow

- The AI requests a meeting; **the human operator provides the meeting URL**.
- The platform sends the invitation (and follow-ups) through the normal job
  queue, then records the outcome.

### Auth & secrets

- Passwords: PBKDF2-HMAC-SHA256 (stdlib, per-user random 256-bit salt).
- Sessions: JWT HS256 in an HttpOnly, SameSite cookie (key derived from
  `SECRET_KEY`). State-changing JSON calls must send
  `X-Requested-With: XMLHttpRequest` (CSRF defence in depth).
- Gmail refresh tokens: encrypted with a Fernet key derived from `SECRET_KEY`
  before being stored in `oauth_credentials` / the token file.

## 5. Design notes and tradeoffs

- **DB-backed queue instead of a broker**: fewer moving parts, transactional
  consistency with campaign state, easy inspection via `/api/queue`, and a
  simple health story. Throughput is moderate by design (paced outreach), so
  PostgreSQL is more than adequate.
- **Custom worker instead of Celery**: the workload is a handful of job types
  with strict ordering and pacing needs; an asyncio loop plus SKIP LOCKED gives
  exactly-once semantics with half the moving parts.
- **Single-process API**: the reverse proxy means the API can stay private;
  CORS is only relevant if you expose the API directly.