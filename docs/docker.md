# Docker / Docker Compose

Everything needed to run the whole product — database, API, workers, dashboard,
and proxy — with one command: `docker compose up -d --build`.

## 1. Service map

| Service | Image / build | Runs | Exposes | Health check |
|---|---|---|---|---|
| `postgres` | `postgres:16-alpine` | PostgreSQL 16 | internal 5432 | `pg_isready` |
| `redis` | `redis:7-alpine` | Redis 7 (AOF enabled) | internal 6379 | `redis-cli ping` |
| `api` | build `./backend` | Gunicorn + uvicorn, FastAPI | internal 8000 | `GET /ready` → 200 |
| `worker` | build `./backend` | `python -m app.workers.worker` | — | `deps_ok` (DB+Redis ping) |
| `scheduler` | build `./backend` | `python -m app.workers.scheduler` | — | `deps_ok` (DB+Redis ping) |
| `frontend` | build `./frontend` | Next.js (`npm run start`) | internal 3000 | `wget /` |
| `reverse-proxy` | `nginx:1.27-alpine` | nginx → api/frontend | **host `HTTP_PORT` (80)** | `wget /health` |

Only `reverse-proxy` publishes a port. Everything else is on the internal
Compose network.

## 2. Images

- **backend image** (`backend/Dockerfile`): `python:3.12-slim` → installs
  requirements → entrypoint runs `alembic upgrade head`
  (skipped when `SKIP_AUTO_MIGRATE=1`) then
  `gunicorn app.main:app -k uvicorn.workers.UvicornWorker -w ${GUNICORN_WORKERS:-2} -b 0.0.0.0:8000`.
  The same image is reused by `worker` and `scheduler` with an overridden
  `command`. `curl` is installed inside the image for the API healthcheck.
- **frontend image** (`frontend/Dockerfile`): multi-stage — `node:24-alpine`
  runs `npm ci && next build` with `NEXT_PUBLIC_API_URL` baked in as a build
  ARG; the runtime stage serves the build with `npm run start` listening on
  `0.0.0.0:${PORT:-3000}`.

## 3. Volumes

| Volume | Mount | Contents |
|---|---|---|
| `pgdata` | `/var/lib/postgresql/data` | PostgreSQL data |
| `redisdata` | `/data` | Redis AOF persistence |
| `appdata` | `/srv/app/data` (api/worker/scheduler) | Gmail OAuth token file (`gmail_token.json`) and other long-lived app files |

`appdata` is included in backups — see [backup.md](backup.md).

## 4. Configuration

The root `.env` file feeds everything (via Compose variable substitution and
`backend/app/config.py`). Start from the template:

```bash
cp .env.example .env
openssl rand -hex 32        # -> SECRET_KEY
```

Key wiring:

- `DATABASE_URL` is composed inside `docker-compose.yml` from the
  `POSTGRES_USER/PASSWORD/DB` variables, pointing at the `postgres` service.
  Local (non-Docker) runs must set `DATABASE_URL`/`REDIS_URL` explicitly.
- `NEXT_PUBLIC_API_URL` defaults to `/api` (relative → same origin via nginx).
  Set it to an absolute URL only if you serve the frontend from another origin.
- `SECRET_KEY` has no default in Compose: `docker compose up` fails fast if it
  is missing, which prevents accidental production boots with a default key.

## 5. Health checks

- `api` → `GET /ready` (root level): 200 `{"status":"ok",...}` only when both
  PostgreSQL and Redis respond; otherwise 503 `{"status":"degraded", ...}` —
  the healthcheck treats only 200 as healthy.
- `worker`/`scheduler` → `python -m app.workers.deps_ok`, a tiny check that
  pings DB and Redis and exits 0/1.
- `reverse-proxy` → `wget /health` through the proxy itself, so the whole
  user-facing path is verified.

See `docker compose ps` and `docker compose inspect --format ...` for status.

## 6. Common operations

```bash
docker compose up -d --build          # build + start everything
docker compose ps                     # status incl. health
docker compose logs -f api worker     # follow logs
docker compose restart worker         # restart one service
docker compose up -d --scale worker=2 # run a second worker (SKIP LOCKED safe)
docker compose down                   # stop (data volumes persist)
docker compose down -v                # stop AND delete volumes (destructive!)
docker compose config                 # validate + show resolved config
docker compose exec postgres psql -U outreach -d outreach   # psql shell
```

## 7. Local development without Docker

See [development.md](development.md). In short: run PostgreSQL + Redis (or
point the app at an existing instance), `alembic upgrade head`, then start
`uvicorn`, the worker, the scheduler, and the Next.js dev server.

## 8. Validation notes (this repository)

- `docker-compose.yml` passes `docker compose config` (7 services, anchors
  resolve, no schema errors).
- `backend/Dockerfile` and `frontend/Dockerfile` follow current image tags
  (`python:3.12-slim`, `node:24-alpine`) and were validated at the text level
  (no Docker daemon in the build environment). Run one `docker compose build`
  on a machine with Docker to confirm before the first production deploy.
- The nginx configuration passed `nginx -t`.