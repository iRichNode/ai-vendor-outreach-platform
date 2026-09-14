# AI Vendor Outreach Platform

A self-hosted, AI-assisted **vendor outreach automation SaaS**. Find and research
vendors, run paced email campaigns through Gmail, let an AI assistant hold
qualification conversations with leads, escalate to a human when needed, and
track everything from a Next.js dashboard.

Built to run 24/7 on a single VPS with Docker Compose.

```
Frontend (Next.js)  ──►  Reverse proxy (nginx)  ──►  API (FastAPI)  ──►  PostgreSQL + Redis
                                                    │
                                                    ├─► Worker  (outbound job dispatcher, DB-backed queue)
                                                    └─► Scheduler (queue maintenance / beat role)
```

---

## Features

**Vendors**
- Manual creation, bulk paste, and CSV import with duplicate detection
- Discovery from permitted public/business sources (extensible provider)
- Website research (politeness-limited) and status workflow
  (NEW → RESEARCHED → READY_TO_CONTACT → CONTACTED → REPLIED → …)

**Campaigns**
- Paced sending: batch size, min/max delay, daily cap, business-hours window
- Configurable follow-up sequences (subject + body + days after)
- Per-vendor opt-out, per-vendor pause, campaign pause/resume, global pause

**Conversations**
- Inbound Gmail replies show up in the conversation thread
- AI replies with configurable delay, intent detection
  (interested / not interested / opt-out / meeting request / needs human…)
- Human takeover any time; AI never creates meetings or calendar events

**Meetings**
- AI detects vendor interest and requests a meeting
- **The human operator provides the meeting URL** (AI cannot create meetings)
- Invitation and follow-up emails are dispatched by the worker

**Operations**
- Real-time queue view (`scheduled_jobs`, PostgreSQL-backed, idempotent)
- Telegram operator notifications (interested / qualified / needs help)
- Analytics (send volume, reply rate, meetings, funnel)
- Health endpoints `/health` (liveness) and `/ready` (DB + Redis)

---

## Requirements

- Docker 24+ with the Compose plugin, or a machine with Python 3.13+/Node 24+
- A VPS (1 GB RAM is enough for small volumes; 2 GB recommended)
- Optional external accounts: Gmail API, OpenRouter (AI), Telegram bot

## Quick start (Docker, recommended)

```bash
git clone https://github.com/iRichNode/ai-vendor-outreach-platform.git
cd ai-vendor-outreach-platform
cp .env.example .env
nano .env                # set SECRET_KEY (openssl rand -hex 32) and integrations
docker compose up -d --build
```

Then open http://localhost (or your VPS IP). On first boot:

1. `docker compose ps` — all 7 services healthy
2. Visit `/` — the setup wizard creates the first admin
   (or set `INITIAL_ADMIN_*` in `.env` before first boot)
3. `curl http://localhost/ready` returns `{"status":"ok",...}`

For scripted installs on Ubuntu: `sudo bash scripts/install.sh`
See [docs/deployment.md](docs/deployment.md) for HTTPS (Let's Encrypt) and
updates, and [docs/docker.md](docs/docker.md) for the full service map.

## Local development (no Docker)

```bash
# Backend (PostgreSQL + Redis must be reachable)
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL=postgresql+asyncpg://outreach:outreach@127.0.0.1:5432/outreach
export REDIS_URL=redis://127.0.0.1:6379/0
export SECRET_KEY=dev-only-secret-key-0123456789abcdef
alembic upgrade head
uvicorn app.main:app --reload          # http://127.0.0.1:8000/api/docs

# Worker + scheduler (separate terminals)
python -m app.workers.worker
python -m app.workers.scheduler

# Frontend
cd ../frontend
npm ci
NEXT_PUBLIC_API_URL=http://127.0.0.1:8000 npm run dev   # http://localhost:3000
```

## Environment variables

Every setting is documented in [.env.example](.env.example) and loaded by
`backend/app/config.py`. Groups:

| Group | Variables |
|---|---|
| Core | `SECRET_KEY`, `ENVIRONMENT`, `DEBUG`, `BASE_URL`, `CORS_ORIGINS`, `DEMO_MODE` |
| Database / queue | `DATABASE_URL`, `REDIS_URL`, `POSTGRES_*` (compose) |
| Initial admin | `INITIAL_ADMIN_USERNAME/PASSWORD/EMAIL` |
| AI | `OPENROUTER_API_KEY`, `LLM_MODEL`, `LLM_TEMPERATURE`, `AI_REPLY_*` |
| Gmail | `GOOGLE_CLIENT_ID/SECRET/REDIRECT_URI`, `GMAIL_TRANSPORT`, `GMAIL_SENDER_*` |
| Discovery | `DISCOVERY_PROVIDER/API_URL/API_KEY`, `RESEARCH_*` |
| Telegram | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` |
| Pacing | `SEND_*`, `DAILY_MAX_EMAILS`, `SENDING_*`, `CAMPAIGN_TIMEZONE` |
| Worker/scheduler | `DISPATCH_INTERVAL_SECONDS`, `SCHEDULER_*`, `JOB_*`, `GUNICORN_WORKERS` |
| Proxy | `HTTP_PORT`, `NEXT_PUBLIC_API_URL` |

## Gmail setup

The platform sends through the **Gmail API** (preferred) or SMTP.

1. **Google Cloud OAuth** — create a project, enable the Gmail API, add the
   redirect URI (`https://<your-domain>/api/integrations/gmail/oauth/callback`
   or `http://127.0.0.1:8000/...` for local dev), create an OAuth client.
2. Put `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI` in `.env`.
3. In the dashboard: **Settings → Gmail → Connect**. A token is stored in the
   persistent app data volume (compose) or `GMAIL_TOKEN_FILE` (local).
4. `GMAIL_TRANSPORT=auto` uses the API when credentials exist and falls back to
   `fake` (dry-run) otherwise — nothing sends mail until you connect.

See [docs/deployment.md](docs/deployment.md) § "Gmail & OAuth" for details.

## OpenRouter (AI) setup

1. Create an account at openrouter.ai and generate an API key.
2. Set `OPENROUTER_API_KEY` in `.env` (any OpenAI-compatible endpoint works via
   `OPENROUTER_BASE_URL`).
3. Pick a model with `LLM_MODEL` (default `openai/gpt-4o-mini`).

Without a key the AI services fail safe: conversations stay in
`NEEDS_REVIEW`, nothing is invented.

## Telegram setup

1. Talk to @BotFather → create a bot → get the token.
2. Message your bot once, then find your chat id (e.g. via
   `https://api.telegram.org/bot<TOKEN>/getUpdates`).
3. Set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in `.env`.

Operator notifications fire for: interested/qualified vendors, meeting
requests, AI needing help, and errors.

## VPS deployment & HTTPS

See [docs/deployment.md](docs/deployment.md):

- `scripts/install.sh` — validates Docker, configures `.env`, builds and
  starts the stack, waits for health, reports status (non-destructive)
- HTTPS: `docker compose` + certbot with an nginx 443 listener, or put the
  stack behind Caddy/Traefik/Cloudflare — the proxy respects `X-Forwarded-Proto`

## Backups

See [docs/backup.md](docs/backup.md). In short:

```bash
scripts/backup.sh                      # pg_dump to ./backups/ + app-data tar
scripts/restore.sh backups/ai_vendor_outreach_<timestamp>.dump.gz
```

## Updating

```bash
git pull
docker compose build --pull
docker compose up -d
```

Alembic migrations run automatically on API container start (idempotent).
Set `SKIP_AUTO_MIGRATE=1` and run `docker compose exec api alembic upgrade head`
for controlled multi-host deploys.

## Testing

```bash
cd backend
pip install -r requirements.txt
DATABASE_URL=postgresql+asyncpg://outreach:outreach@127.0.0.1:5432/outreach \
REDIS_URL=redis://127.0.0.1:6379/0 \
SECRET_KEY=test-key pytest -q        # 26 tests, mocked Gmail/Telegram/AI

cd ../frontend
npm ci && npm run build              # type-checked production build
```

See [docs/testing.md](docs/testing.md) for the API smoke suite and coverage.

## Repository layout

```
backend/          FastAPI app (api/, models/, services/, workers/, alembic/)
frontend/         Next.js dashboard (app/, lib/, components/)
worker/           worker service notes (runs backend image)
scheduler/        scheduler service notes (runs backend image)
infra/nginx/      reverse proxy configuration
scripts/          install.sh, backup.sh, restore.sh, status.sh
docs/             architecture, API, deployment, docker, backup, testing, security
docker-compose.yml
```

## Security

- Passwords hashed with PBKDF2-HMAC-SHA256 (600k iterations)
- Login sessions: signed HttpOnly JWT cookie (`adv_session`), same-site lax
- CSRF protection on every state-changing JSON request
- Rate limiting on auth endpoints; input validation via Pydantic
- No secrets in the repository; `.env` is git-ignored (see [docs/security.md](docs/security.md))
- Health endpoints expose no internals; the API exception handler never leaks tracebacks

## Troubleshooting

| Symptom | Fix |
|---|---|
| `docker compose up` hangs on api healthcheck | `docker compose logs api` — usually `DATABASE_URL`/`SECRET_KEY` missing from `.env` |
| Login works, dashboard APIs 403 | Missing `X-Requested-With` on custom clients; the dashboard sends it automatically (CSRF guard) |
| Emails never send | Set `GMAIL_TRANSPORT`/credentials; check `docker compose logs worker`; jobs appear in the Queue page when enqueued |
| `POSTGRES_USER` password changed but stack won't start | `docker compose down -v` (deletes volumes), then `up -d` — do NOT run `-v` on a production box without a backup |
| Port 80 busy | change `HTTP_PORT` in `.env`, or disable the conflicting service |

See [docs/architecture.md](docs/architecture.md) for design decisions
(including why the queue is PostgreSQL-backed instead of Celery/RabbitMQ).

## License

MIT — see [LICENSE](LICENSE).