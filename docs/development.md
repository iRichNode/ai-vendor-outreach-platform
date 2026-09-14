# Development

Local development without Docker. You need Python 3.13+ and Node 24+ (the repo
was developed against Python 3.14 / Node 24), plus PostgreSQL and Redis
reachable at `127.0.0.1`.

## 1. One-time setup

```bash
# PostgreSQL + Redis (example, Debian/Ubuntu)
sudo apt install -y postgresql redis-server
sudo -u postgres psql -c "CREATE USER outreach WITH PASSWORD 'outreach';"
sudo -u postgres createdb -O outreach outreach

# Backend
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp ../.env.example ../.env        # optional: edit values
export DATABASE_URL=postgresql+asyncpg://outreach:outreach@127.0.0.1:5432/outreach
export REDIS_URL=redis://127.0.0.1:6379/0
export SECRET_KEY=dev-only-secret-key-0123456789abcdef

# Frontend
cd ../frontend
npm ci
```

> In `development` mode the API also runs `create_all` at startup, so an empty
> database works without migrations; for a production-like schema run
> `alembic upgrade head`.

## 2. Run the stack (four terminals)

```bash
# 1) API
cd backend && source .venv/bin/activate && uvicorn app.main:app --reload
#    Swagger at http://127.0.0.1:8000/api/docs

# 2) Worker (outbound dispatcher)
cd backend && source .venv/bin/activate && python -m app.workers.worker

# 3) Scheduler (queue maintenance)
cd backend && source .venv/bin/activate && python -m app.workers.scheduler

# 4) Frontend
cd frontend && NEXT_PUBLIC_API_URL=http://127.0.0.1:8000 npm run dev
#    Dashboard at http://localhost:3000
```

## 3. Project layout

```
backend/
  app/
    main.py              # FastAPI app, probes, error handler
    config.py            # pydantic-settings, reads .env
    database.py          # async engine/session, init_db
    api/                 # route modules (auth, vendors, campaigns, ...)
    core/                # auth deps, security (hashing/JWT/Fernet), ratelimit
    models/              # SQLAlchemy models (13 tables)
    schemas/             # Pydantic request/response models
    services/            # business logic (pacing, queue, gmail, ai, ...)
    workers/
      worker.py          # job dispatcher loop
      scheduler.py       # reclaim/prune maintenance loop
      deps_ok.py         # healthcheck helper
  alembic/               # migrations (initial: b14fd4c0615e)
  tests/                 # pytest suite (26 tests)
  requirements.txt
frontend/
  app/                   # Next.js pages (login, dashboard, vendors, ...)
  lib/api.ts             # API base URL handling
infra/nginx/             # proxy config
scripts/                 # install/backup/restore/status
docs/                    # this documentation
```

## 4. Add a database migration

```bash
cd backend && source .venv/bin/activate
alembic revision --autogenerate -m "describe change"
# review the generated file, then:
alembic upgrade head
```

## 5. Run tests

```bash
cd backend && source .venv/bin/activate
pytest -q
```

Tests use their own database (see `tests/conftest.py`) and drop/recreate the
`public` schema — **never point them at data you care about**. See
[testing.md](testing.md).

## 6. Frontend conventions

- `NEXT_PUBLIC_API_URL` is read at build time: `/api` (relative, compose
  default) or an absolute URL for standalone dev.
- The Next.js app is served by `next start` in production (works without
  `output: standalone`); use `npm run start -- -p PORT` to change ports
  (npm requires `--` to avoid eating the flag).

## 7. Environment variables

Every variable is documented in [.env.example](../.env.example) and loaded by
`backend/app/config.py`. For development the important ones are
`DATABASE_URL`, `REDIS_URL`, and `SECRET_KEY`; everything else has safe
defaults (`DEMO_MODE=true` gives dry-run behavior everywhere: fake Gmail,
demo discovery provider, no real sends).

## 8. Common dev tasks

| Task | Command |
|---|---|
| Reset dev DB | `psql ... -c 'DROP SCHEMA public CASCADE; CREATE SCHEMA public;'` then `alembic upgrade head` |
| Follow queue | `psql -d outreach -c 'select * from scheduled_jobs order by created_at desc limit 20;'` |
| Retry a job | API `POST /api/queue/retry` from the dashboard |
| Inspect audit trail | `select * from audit_logs order by created_at desc limit 20;` |
| Format/lint | the repo uses standard tooling expectations; keep code isort+black-clean |