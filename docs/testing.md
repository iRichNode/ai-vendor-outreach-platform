# Testing

## 1. Backend test suite

The suite lives in `backend/tests/` and runs with pytest against a real
PostgreSQL (async SQLAlchemy + asyncpg, no mocks for the database layer) with
Redis available for rate-limit/integration tests.

```bash
cd backend
source .venv/bin/activate
pytest -q            # 26 tests, all passing
pytest -q -x         # stop at first failure
pytest -q -k queue   # run only queue-related tests
```

> **⚠ Important**: the test fixture `DROP`s and recreates the `public` schema
> of the configured database. Point tests at a **dedicated database**
> (e.g. `outreach_test`), never the production one. After a test run against a
> development database, re-apply the schema:
> `alembic upgrade head` (tables are not automatically recreated for you).

Test configuration lives in `backend/tests/conftest.py`; the fixture overrides
`DATABASE_URL`/`REDIS_URL` before application imports happen.

## 2. What is covered

- **Auth**: login, wrong password, logout, session validity, CSRF header
  requirement, rate limiting.
- **Vendors**: CRUD, bulk import with duplicate detection, CSV import,
  search/filter, status workflow transitions.
- **Campaigns**: create/update, attach vendors, start/pause/resume,
  pacing defaults, per-vendor opt-out and pause respected by dispatch.
- **Queue**: enqueue, dialect-aware SKIP LOCKED claiming (no double-claim),
  idempotency key uniqueness, retry, cancel.
- **Conversations/meetings**: message flow, human takeover, AI-never-creates
  meetings rule (meeting requests require an operator-provided URL).
- **Health**: `/health` liveness, `/ready` degraded → 503 with structured body.
- **Schema integrity**: foreign keys enforced (e.g. `scheduled_jobs.vendor_id`
  rejects unknown vendors).

## 3. Manual smoke-test checklist

After a local run or deployment, verify the happy path end to end:

- [ ] `GET /health` → 200 and `GET /ready` → 200 `{"status":"ok",...}`
- [ ] Setup wizard or `INITIAL_ADMIN_*` created the first admin; log in via UI
- [ ] Create a vendor → appears in the vendors table
- [ ] Create a campaign, attach the vendor, start it
- [ ] `GET /api/queue` shows a pending job; within one
      `DISPATCH_INTERVAL_SECONDS` the worker claims + completes (fake transport
      keeps results dry-run)
- [ ] Conversation thread increments when the worker simulates inbound mail
- [ ] Settings changes persist after an API restart
- [ ] `docker compose restart worker scheduler` — queue continues
      (stale-claim reclaim works)

## 4. Worker/scheduler functional tests (done during development)

- Reclaim: a `CLAIMED` job older than `JOB_STALE_AFTER_SECONDS` moved back to
  `PENDING` with its `claim_uuid` cleared and `attempts+1`. ✅ verified on a
  scratch database.
- Prune: `COMPLETED` older than `JOB_RETENTION_DAYS` removed; recent
  `COMPLETED` kept. ✅ verified.
- Fresh-clone test: see the repository README / `.github` (if present) — the
  sequence clone → `npm ci`/`pip install` → `alembic upgrade head` → run →
  smoke cases was executed during release validation.

## 5. Frontend checks

- `cd frontend && npm ci && npm run build` — production build must succeed
  with `NEXT_PUBLIC_API_URL` set (relative `/api` for compose).
- `npm run start -- -p 3100` — the runtime server accepts an explicit port
  (note the `--` so npm does not swallow the flag).
- Manual UI pass: the eleven screens (login, dashboard, vendors,
  find-vendors, campaigns, conversations, queue, meetings, notifications,
  analytics, settings) render with no console errors against a live API.