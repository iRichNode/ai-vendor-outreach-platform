# Security

Hardening notes for the AI Vendor Outreach Platform. This is a hobby/small-VPS
product; the controls below are appropriate for that threat model
(opportunistic attackers, credential stuffing, leaked tokens) and are
documented so operators can raise the bar further.

## 1. Secrets management

- **No secrets in the repository.** `.env` and `.env.*` are git-ignored
  (only `.env.example` is committed, with placeholder values). Before release
  the tree is scanned for `ghp_`, `sk-`, PEM keys, and common token patterns.
- `SECRET_KEY` is *required* by Compose (no default): the stack refuses to
  start without it. Generate with `openssl rand -hex 32`. Rotate by changing
  it and restarting (sessions and encrypted tokens are derived from it, so
  rotation logs everyone out and requires re-encrypting stored OAuth tokens).
- Gmail API secrets live in `GOOGLE_CLIENT_*` env vars only; refresh tokens are
  stored **encrypted at rest** with a Fernet key derived from `SECRET_KEY`
  (`backend/app/core/security.py`).
- The Gmail token file lands in the `appdata` volume inside the container, not
  in the image.

## 2. Authentication & sessions

- Passwords hashed with **PBKDF2-HMAC-SHA256** (stdlib), 256-bit random salt
  per user, iteration count from `PASSWORD_ITERATIONS` (default 600k).
- Sessions: **JWT HS256** in an **HttpOnly, SameSite=Lax** cookie; the signing
  key is derived from `SECRET_KEY`. Tokens carry `iat`/`exp` and a `type`
  claim.
- **CSRF**: SameSite=Lax blocks cross-site cookie delivery, and state-changing
  JSON calls additionally require `X-Requested-With: XMLHttpRequest` (403
  without it).
- `COOKIE_SECURE=true` once HTTPS is enabled (default in the Docker compose env).
- Optional `INITIAL_ADMIN_*` first-boot provisioning; otherwise the UI's setup
  wizard creates the admin (and the setup endpoint is disabled afterwards).

## 3. Network & transport

- Reverse proxy publishes **only** port 80 (or 443 with the TLS recipe in
  [deployment.md](deployment.md)); the API, workers, DB, and Redis are not
  exposed to the public interface (Compose creates a private network).
- PostgreSQL and Redis listen on the internal network only; both have their own
  credentials/variables.
- CORS is restricted to `CORS_ORIGINS` (default same-origin via proxy). If you
  expose the API directly, set `CORS_ORIGINS` to your actual dashboard origin.
- Recommend keeping `ENVIRONMENT=production` and `DEBUG=false` in `.env`
  (production compose defaults). The API hides internal errors behind a
  generic 500 handler.

## 4. Abuse & injection

- **Rate limiting** on auth and sensitive endpoints via Redis
  (`backend/app/core/ratelimit.py`), 429 on overflow.
- **SQL injection**: the API uses SQLAlchemy Core/ORM parameter binding; the
  worker uses the same models. No string-built SQL in the app layer.
- **Vendor website research** is politeness-limited (`RESEARCH_TIMEOUT_SECONDS`,
  `RESEARCH_POLITENESS_SECONDS`), single host per job, bounded response sizes —
  treat third-party websites as untrusted input.
- **AI output** is a product feature: AI-generated messages are queued jobs
  like any other, run through the same per-vendor opt-out/pause checks, and the
  AI is structurally prevented from creating meetings/calendar events
  (operator must supply the meeting URL).

## 5. Queue integrity

- Idempotency keys with a UNIQUE constraint: a job cannot be enqueued twice
  even if a retry races.
- SKIP LOCKED claiming prevents double-send under concurrent workers.
- The scheduler reclaims stale claims and prunes old terminal rows
  (`JOB_RETENTION_DAYS`), so failure modes self-heal and the table stays
  bounded.
- Audit log (`audit_logs`) records sensitive actions (admin changes, OAuth
  lifecycle, setting changes) for later review.

## 6. Dependency & update hygiene

- Pin dependencies in `backend/requirements*.txt` and `frontend/package-lock.json`
  (commit the lockfile).
- Renew images frequently: `docker compose up -d --build && docker image prune -f`,
  `docker compose exec postgres`/`redis` pull tags will update on `up` when you
  run `docker compose pull`.
- Watch `docker compose pull postgres redis reverse-proxy` for distro/base
  image security updates.

## 7. Operational checklist

- [ ] `SECRET_KEY` random 64-hex, present in `.env`, never committed
- [ ] `POSTGRES_PASSWORD` changed; `REDIS` has auth or is network-isolated
- [ ] HTTPS (Let's Encrypt); `BASE_URL` matches; `COOKIE_SECURE=true`
- [ ] Firewall allows only 22/80/443 from the internet
- [ ] Nightly backups, off-site copy, monthly test restore
- [ ] Latest image rebuilds applied; lockfiles committed
- [ ] `DEMO_MODE=false`, `ENVIRONMENT=production`, `GUNICORN_WORKERS` modest
- [ ] Monitor `/ready` externally (DB/Redis degradation is visible)

## 8. Known scope/limitations

- No MFA, no per-role RBAC (single operator role), no audit-log retention
  policy — acceptable for a single-operator SaaS; add before multi-operator
  deployments.
- Gmail scope is narrow (send + read own mail) with a limited watch TTL
  (7 days); refresh handled by the worker.
- Threat model assumed: internet-facing single VPS; not hardened against a
  full OAuth-phishing or supply-chain adversary.