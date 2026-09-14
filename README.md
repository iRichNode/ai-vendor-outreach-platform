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

**VPS (recommended target for the one-shot installer)**

| Spec | Minimum | Recommended |
|---|---|---|
| OS | Ubuntu 22.04 LTS | Ubuntu 24.04 LTS |
| CPU | 1 vCPU | 2 vCPU |
| RAM | 2 GB | 4 GB |
| Disk | 20 GB SSD | 30+ GB SSD |
| Network | Ports 80 and 443 open (firewall / security group) | Ports 80 and 443 open |
| Domain | A record pointing to the server IP | A record pointing to the server IP |

- Docker 24+ with the Compose plugin (installed in Step 2 of the guide below)
- Everything else - AI key, Gmail, Microsoft 365/SMTP, Telegram - can be
  configured **in the web panel after installation**, no SSH/rebuild needed.

## VPS deployment & HTTPS (one-shot installer)  ⭐

Run one command on a fresh VPS and the platform is live on
`https://<your-domain>` - the Let's Encrypt certificate is issued **during
installation** and the app opens from any computer:

```bash
sudo bash scripts/install.sh
```

### Step-by-step installation guide

**Step 0 - VPS**  \
Order a VPS matching the table above (Ubuntu 24.04 LTS, 2 vCPU / 4 GB RAM /
30 GB is a comfortable baseline). Make sure ports **80** and **443** are open
in the firewall / security group; the installer needs them for the challenge.

**Step 1 - connect over SSH**

```bash
ssh root@<server-ip>
```

**Step 2 - install Docker Engine + compose plugin**

```bash
curl -fsSL https://get.docker.com | sh
```

**Step 3 - point your domain at the server**  \
In your DNS provider create an **A record** for your domain (or subdomain) with
"@ / blank name" -> your server's public IPv4. Verify it resolves before
installing:

```bash
dig +short your-domain.com   # -> your server's public IP
```

**Step 4 - clone the repository**

```bash
git clone https://github.com/iRichNode/ai-vendor-outreach-platform.git
cd ai-vendor-outreach-platform
```

**Step 5 - run the installer**

```bash
sudo bash scripts/install.sh
```

It asks two questions and then does everything else unattended:

1. **Domain name** - e.g. `outreach.example.com` (A record already pointing here)
2. **Let's Encrypt email** - for renewal notices
3. *(optional)* create the initial **admin account** now - or skip it and use
   the in-app setup wizard on first login

**Step 6 - open the URL from any computer**

The installer verifies everything and prints:

```
Your platform is live at:  https://your-domain.com
```

Log in with the admin account you created (or complete the wizard), then
configure integrations **in the web panel - no SSH required**:

| What | Where in the panel | What you need |
|---|---|---|
| AI (OpenRouter) | Settings → AI | an OpenRouter API key (openrouter.ai) |
| Gmail | Settings → Email | Google Cloud OAuth client (see below) |
| Microsoft 365 / Outlook / SMTP | Settings → Email | SMTP host, login, sender (see below) |
| Telegram alerts | Settings → Telegram | bot token from @BotFather + your chat id |

### What the installer does (idempotent - safe to re-run)

1. Validates prerequisites (root, git, curl, openssl, Docker + compose, certbot)
2. Creates `.env` from `.env.example` if missing; generates random `SECRET_KEY`
   and `POSTGRES_PASSWORD`; sets `BASE_URL`, `CORS_ORIGINS` and
   `GOOGLE_REDIRECT_URI` to `https://<your-domain>`
3. Starts the stack (HTTP) - port 80 also serves the ACME challenge
4. Issues the **Let's Encrypt certificate during installation** with
   `certbot certonly --webroot` against the running nginx
5. Renders the TLS `ssl.conf`, reloads nginx, verifies `https://<domain>/ready`
6. Installs **auto-renewal**: systemd timer `avop-renew` (daily 03:17) or a
   cron fallback; manual: `sudo bash scripts/renew-cert.sh`

Re-run the installer anytime to recover from a failed issuance (e.g. DNS was
not propagated yet), change the domain, or complete an interrupted setup.

See [docs/deployment.md](docs/deployment.md) for details, and
[docs/backup.md](docs/backup.md) for backups.

## Quick start (Docker, local / without a domain)

```bash
git clone https://github.com/iRichNode/ai-vendor-outreach-platform.git
cd ai-vendor-outreach-platform
cp .env.example .env
nano .env                # set SECRET_KEY (openssl rand -hex 32) and integrations
docker compose up -d --build
```

Then open http://localhost. On first boot:

1. `docker compose ps` — all 7 services healthy
2. Visit `/` — the setup wizard creates the first admin
   (or set `INITIAL_ADMIN_*` in `.env` before first boot)
3. `curl http://localhost/ready` returns `{"status":"ok",...}`

For HTTPS behind the stack without the installer (custom proxy/CDN) or for a
manual certbot setup, see [docs/deployment.md](docs/deployment.md); and
[docs/docker.md](docs/docker.md) for the full service map.

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
| SMTP (Microsoft 365 etc.) | `SMTP_HOST/PORT/USERNAME/PASSWORD/FROM_EMAIL/FROM_NAME/USE_TLS` |
| Discovery | `DISCOVERY_PROVIDER/API_URL/API_KEY`, `RESEARCH_*` |
| Telegram | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` |
| Pacing | `SEND_*`, `DAILY_MAX_EMAILS`, `SENDING_*`, `CAMPAIGN_TIMEZONE` |
| Worker/scheduler | `DISPATCH_INTERVAL_SECONDS`, `SCHEDULER_*`, `JOB_*`, `GUNICORN_WORKERS` |
| Proxy / TLS | `HTTP_PORT`, `HTTPS_PORT`, `LETSENCRYPT_EMAIL`, `NEXT_PUBLIC_API_URL` |

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

Most of this is optional at install time: after a VPS install the redirect URI
is already set for you, and the credentials can be entered in the web panel
(**Settings → Email**) instead of `.env`.

See [docs/deployment.md](docs/deployment.md) § "Gmail & OAuth" for details.

## SMTP setup (Microsoft 365 / Outlook / any provider)

Sending can also go through standard SMTP with STARTTLS (the Gmail transport
falls back to SMTP when configured):

1. Use the web panel (**Settings → Email**) after install, or set in `.env`:
   `SMTP_HOST`, `SMTP_PORT=587`, `SMTP_USERNAME`, `SMTP_PASSWORD`,
   `SMTP_FROM_EMAIL`, `SMTP_FROM_NAME`, `SMTP_USE_TLS=true`
2. Microsoft 365 / Outlook.com: enable SMTP AUTH for the mailbox, use the
   mailbox address as login and the app password; port 587 + STARTTLS
3. Test with **Settings → Email → Send test** before launching a campaign

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


## Updating

```bash
cd ai-vendor-outreach-platform
git pull
docker compose build --pull
docker compose up -d
# TLS certificate renewal stays automatic; manual: sudo bash scripts/renew-cert.sh
```

Alembic migrations run automatically on API container start (idempotent).
Set `SKIP_AUTO_MIGRATE=1` and run `docker compose exec api alembic upgrade head`
for controlled multi-host deploys.

## Backups

See [docs/backup.md](docs/backup.md). In short:

```bash
scripts/backup.sh                      # pg_dump to ./backups/ + app-data tar
scripts/restore.sh backups/ai_vendor_outreach_<timestamp>.dump.gz
```

## Testing

```bash
cd backend
pip install -r requirements.txt
DATABASE_URL=postgresql+asyncpg://outreach:outreach@127.0.0.1:5432/outreach \
REDIS_URL=redis://127.0.0.1:6379/0 \
SECRET_KEY=test-key pytest -q        # 50 tests, mocked Gmail/Telegram/AI

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
infra/nginx/      reverse proxy configuration (TLS templates; ssl.conf is generated)
scripts/          install.sh, renew-cert.sh, backup.sh, restore.sh, status.sh
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