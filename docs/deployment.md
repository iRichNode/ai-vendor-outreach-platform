# Deployment

Production deployment guide for a single VPS. The one-shot installer takes a
fresh Ubuntu server from zero to `https://your-domain` — **including the Let's
Encrypt certificate, issued during installation** — so the app is reachable
from any computer as soon as the script finishes.

> Short version: point DNS at the server, `git clone`, `sudo bash scripts/install.sh`.

## 1. Prerequisites

| Requirement | Detail |
|---|---|
| VPS | Ubuntu 22.04 or 24.04 LTS, **1–2 vCPU, 2–4 GB RAM, 20–30 GB SSD** (see [README Requirements](../README.md#requirements)) |
| Domain | An A record (or AAAA) pointing at the server's public IP — the installer verifies this before issuing a certificate |
| Docker | Docker Engine 24+ **with the Compose plugin** (installed below) |
| Ports | **80 and 443 must be open** in the firewall / cloud security group; 80 serves the ACME challenge during installation |
| Email | A working address for Let's Encrypt expiration notices (prompted during install) |

Install Docker (Debian/Ubuntu):

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker "$USER"   # log out and back in afterwards
docker compose version            # verify
```

## 2. One-shot install (recommended)

The installer does everything in one run: configures the domain, generates
`.env` with strong random secrets, starts the stack, **issues a Let's Encrypt
certificate over HTTP-01**, switches nginx to HTTPS, installs automatic
renewal, and prints the final URL.

```bash
git clone https://github.com/iRichNode/ai-vendor-outreach-platform.git
cd ai-vendor-outreach-platform
sudo bash scripts/install.sh
```

During the run you will be asked for:

1. **Domain name** — e.g. `outreach.example.com` (must already resolve to this
   server).
2. **Let's Encrypt email** — for renewal/expiration notices.
3. **Initial admin account** (optional) — username, password, email. Skipping
   it lets the web-panel setup wizard create the admin later.

What the script does, step by step:

1. **Validates prerequisites** — root, git, curl, openssl, docker; auto-installs
   `certbot` if missing.
2. **Configures the domain** — writes `.env` (or keeps your existing one),
   generates a random `SECRET_KEY` + `POSTGRES_PASSWORD` if still placeholders,
   and points `BASE_URL`, `CORS_ORIGINS`, `GOOGLE_REDIRECT_URI` at
   `https://your-domain`. Optionally writes the initial-admin bootstrap.
3. **DNS sanity check** — compares the domain's A record against the server's
   public IP and warns if they do not match.
4. **Starts the stack over HTTP** (port 80 also serves ACME challenges) and
   waits for `GET /ready` to return 200.
5. **Issues the certificate** — `certbot certonly --webroot`, stored in the
   repo's `infra/certs/etc/letsencrypt/` so it survives `compose down`.
6. **Enables HTTPS** — renders `infra/nginx/conf.d/ssl.conf` from
   `ssl.conf.tpl`, reloads the reverse proxy, verifies `https://your-domain/ready`.
7. **Installs auto-renewal** — a systemd timer `avop-renew` (daily 03:17, with
   `Persistent=true` + `RandomizedDelaySec`) running `scripts/renew-cert.sh`;
   falls back to a cron job on non-systemd hosts.

When it finishes you get:

```
Installation complete

  Your platform is live at:

      https://your-domain
```

Open that URL from any computer, log in, and configure integrations in the web
panel (**no SSH needed** for the rest):

- **Settings → AI** — paste your OpenRouter API key (or any OpenAI-compatible provider)
- **Settings → Email** — connect Gmail via OAuth, or add SMTP (Microsoft 365 / Outlook / any provider)
- **Settings → Telegram** — paste the bot token + chat id

See [README](https://github.com/iRichNode/ai-vendor-outreach-platform#readme)
integration sections and the [Security notes](security.md) for each transport.

### Idempotent re-runs

The installer is safe to re-run: existing certificates are detected and
skipped, `.env` values are kept, services are only started. Re-run it to fix
DNS, pick a new domain, or complete an interrupted installation.

### Automation / non-interactive overrides

CI and automation can pre-seed every prompt via environment variables:

| Variable | Effect |
|---|---|
| `DOMAIN=example.com` | skip the domain prompt |
| `LETSENCRYPT_EMAIL=you@x.co` | skip the email prompt (needed for issuance; otherwise read from `.env`) |
| `NO_PROMPT=1` | never ask; use env values or defaults |
| `SKIP_BUILD=1` | start without rebuilding images (faster re-runs) |
| `SKIP_DNS_CHECK=1` | don't verify the domain resolves to this server |
| `SKIP_RENEWAL=1` | don't install the renewal timer/cron |
| `NO_WAIT=1` | (testing only) skip readiness wait loops |

Example fully automatic run:

```bash
DOMAIN=outreach.example.com LETSENCRYPT_EMAIL=admin@example.com \
  sudo bash scripts/install.sh
```

## 3. Certificate renewal

Renewal is automatic once the installer finishes:

- **systemd** (default on Ubuntu): `avop-renew.timer` runs
  `scripts/renew-cert.sh` daily at 03:17 (randomized ±15 min, catch-up on missed
  runs). Inspect with `systemctl status avop-renew.timer`.
- **cron fallback**: `17 3 * * * /path/to/scripts/renew-cert.sh`.
- **Manual**: `sudo bash scripts/renew-cert.sh` — reuses the webroot method,
  reloads nginx only when a certificate was actually renewed.

Certificates live in `infra/certs/` (git-ignored); back them up together with
`backups/` if you clone the repo fresh (see [backup.md](backup.md)).

## 4. First boot

1. `docker compose ps` — all services should be `healthy`.
2. `curl -s https://your-domain/health` → `{"status":"ok",...}`
3. `curl -s https://your-domain/ready` → 200 `{"status":"ok",...}` (verifies DB + Redis)
4. Open `https://your-domain/` and log in (setup wizard, or the admin created
   during install). If you bootstrapped `INITIAL_ADMIN_USERNAME/PASSWORD/EMAIL`
   (all three together) the first API start creates the account.

## 5. Changes to environment variables

All runtime configuration is either in `.env` or the web panel. After editing
`.env` (e.g. SMTP credentials):

```bash
docker compose up -d --build
```

Note: `BASE_URL`, `CORS_ORIGINS` and the Gmail OAuth redirect URI are managed by
the installer and should stay at `https://your-domain`; the Gmail callback
endpoint is `/api/integrations/gmail/oauth/callback`.

## 6. Updates

```bash
cd ai-vendor-outreach-platform
git pull
docker compose build --pull
docker compose up -d
docker image prune -f          # remove old images
```

Migrations run automatically on API container start (Alembic `upgrade head`;
disable with `SKIP_AUTO_MIGRATE=1` if you manage migrations yourself).
Certificate renewal keeps working — the timer points at the same
`scripts/renew-cert.sh` path. Back up first — see [backup.md](backup.md).

## 7. Backups & monitoring

- Install a nightly backup job (see [backup.md](backup.md)) and copy the
  `backups/` directory off-site.
- Monitor `/ready` from outside the stack (e.g. Uptime Kuma or a cron curl):

```bash
*/5 * * * * curl -fsS https://your-domain/ready >/dev/null || logger -t outreach "ready check FAILED"
```

- Watch logs: `docker compose logs -f api worker scheduler`

## 8. Scaling notes

- One VPS runs the whole stack today. If send volume grows:
  - Raise `GUNICORN_WORKERS` (API) — keep workers × threads modest on 2–4 GB.
  - Start additional `worker` replicas via
    `docker compose up -d --scale worker=2` — SKIP LOCKED keeps them safe.
  - Tune `DISPATCH_INTERVAL_SECONDS`, `SCHEDULER_INTERVAL_SECONDS` and pacing
    variables instead of raising concurrency: this app is intentionally paced.

## 9. Troubleshooting

### Certificate issuance fails during install

The stack stays up at `http://your-domain`; fix and re-run the installer
(idempotent). Common causes:

| Cause | Fix |
|---|---|
| A record points elsewhere / not propagated | Fix DNS at your registrar, wait for propagation (`dig A your-domain`), re-run |
| Port 80 blocked by firewall/security group | Open 80 (and 443) to the internet; re-run |
| `http://your-domain/.well-known/acme-challenge/<token>` unreachable | The webroot is served by nginx at `/var/www/certbot` — make sure no other server answers port 80 |

### Other symptoms

| Symptom | Likely fix |
|---|---|
| `/ready` returns 503 `degraded` | Check Postgres/Redis health; look at the `problems` array in the response |
| `api` never becomes healthy | `docker compose logs api`; check `SECRET_KEY` is set (compose fails fast if not) |
| Frontend shows `Not Found` on login (network tab: `/api/api/...`) | Doubled `/api` prefix from an old build; ensure `NEXT_PUBLIC_API_URL` is empty/absent, then `docker compose build frontend && docker compose up -d frontend` |
| Gmail OAuth token lost | It lives in the `appdata` volume (`/srv/app/data/gmail_token.json`); restore from your appdata backup |
| Certificate expired / renewal failed | `journalctl -u avop-renew.service`; port 80 must stay open for the webroot challenge |
| Migrations run twice | They are idempotent (Alembic version table); safe |
| `docker compose up` complains `SECRET_KEY` | `.env` missing or variable empty — re-run `scripts/install.sh`, or `cp .env.example .env` and generate a key |

## 10. Security checklist (summary)

Full details in [security.md](security.md):

- [ ] HTTPS enabled with a valid Let's Encrypt certificate (auto-renewed)
- [ ] `SECRET_KEY` set to a random 64-hex value, never committed
- [ ] `POSTGRES_PASSWORD` changed from the default
- [ ] `BASE_URL`/`CORS_ORIGINS`/`GOOGLE_REDIRECT_URI` point at `https://your-domain`
- [ ] `DEMO_MODE=false` and `ENVIRONMENT=production`
- [ ] Only port 80/443 open to the public
- [ ] Nightly backups + off-site copy verified by a test restore
