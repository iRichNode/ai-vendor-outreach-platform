#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# AI Vendor Outreach Platform - one-shot VPS installer
#
#   sudo bash scripts/install.sh
#
# Run it on a fresh Ubuntu 22.04/24.04 LTS VPS that has:
#   - Docker Engine + compose plugin installed
#   - an A record (or AAAA) pointing your domain at this server's IP
#   - ports 80 and 443 open to the internet (firewall / security group)
#
# The installer is idempotent; you can re-run it to fix DNS, pick up a new
# domain, or complete a previously interrupted setup.
#
# What it does:
#   1. Validates prerequisites (root, git, curl, openssl, docker, certbot)
#   2. Configures the domain
#        - prompts for DOMAIN + Let's Encrypt email (or env overrides)
#        - creates .env from .env.example (or keeps the existing one)
#        - generates SECRET_KEY / POSTGRES_PASSWORD if still placeholders
#        - sets BASE_URL / CORS_ORIGINS / GOOGLE_REDIRECT_URI to https://DOMAIN
#        - optional initial-admin bootstrap before first boot
#   3. Starts the stack      (HTTP only - port 80 also serves ACME challenges)
#   4. Issues a Let's Encrypt certificate during installation
#        - certbot certonly --webroot against the running stack
#   5. Enables HTTPS         (renders ssl.conf, reloads nginx, verifies https)
#   6. Installs auto-renewal (systemd timer 'avop-renew', or cron fallback)
#   7. Prints the final URL - ready to open from any computer
#
# Environment overrides (now()-friendly for CI/automation):
#   DOMAIN=example.com          skip the domain prompt
#   LETSENCRYPT_EMAIL=you@x.co  skip the email prompt (required for issuance;
#                               no prompt means it is read from .env)
#   NO_PROMPT=1                 never ask; use env values or defaults
#   SKIP_BUILD=1                start without rebuilding images
#   SKIP_DNS_CHECK=1            don't verify the domain resolves to this server
#   SKIP_RENEWAL=1              don't install the renewal timer/cron
#   NO_WAIT=1                   (testing only) skip readiness wait loops
# ---------------------------------------------------------------------------
set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$(pwd)"
ENV_FILE="$ROOT/.env"
TLS_ROOT="$ROOT/infra/certs"
CERT_CONFIG="$TLS_ROOT/etc/letsencrypt"
CERT_WORK="$TLS_ROOT/work"
CERT_LOGS="$TLS_ROOT/logs"
WEBROOT="$TLS_ROOT/www"
SSL_CONF="$ROOT/infra/nginx/conf.d/ssl.conf"
SSL_TPL="$ROOT/infra/nginx/conf.d/ssl.conf.tpl"

say() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
die() { printf '\033[1;31mERROR: %s\033[0m\n' "$*" >&2; exit 1; }
warn() { printf '\033[1;33mWARNING: %s\033[0m\n' "$*" >&2; }

# prompt "question" [DEFAULT] -> echoes the answer (defaulted when NO_PROMPT=1)
prompt() {
  local q="$1" def="${2:-}" ans ret=0
  if [ "${NO_PROMPT:-0}" = "1" ]; then
    printf '%s\n' "$def"
    return 0
  fi
  if [ -n "$def" ]; then
    read -rp "$q [$def]: " ans || ret=1
  else
    read -rp "$q: " ans || ret=1
  fi
  set +e; [ "$ret" != 0 ] && ans="$def"; set -e
  printf '%s\n' "${ans:-$def}"
}

# upsert_env KEY VALUE - set KEY=VALUE in $ENV_FILE (replace or append)
upsert_env() {
  local key="$1" value="$2"
  if grep -q "^${key}=" "$ENV_FILE"; then
    sed -i "s|^${key}=.*|${key}=${value}|" "$ENV_FILE"
  else
    printf '%s=%s\n' "$key" "$value" >> "$ENV_FILE"
  fi
}

# ---------------- 1. prerequisites ----------------
say "Checking prerequisites"
[ "$(id -u)" = "0" ] || die "Please run as root:  sudo bash scripts/install.sh"
command -v git     >/dev/null || die "git is required:  sudo apt install -y git"
command -v curl    >/dev/null || die "curl is required:  sudo apt install -y curl"
command -v openssl >/dev/null || die "openssl is required:  sudo apt install -y openssl"
command -v docker  >/dev/null || die "docker is required:  https://docs.docker.com/engine/install/ubuntu/"
docker compose version >/dev/null 2>&1 || die "docker compose plugin is required:  sudo apt install -y docker-compose-plugin"
if ! command -v certbot >/dev/null; then
  echo "  certbot not found - installing it (apt)..."
  apt-get install -y certbot >/dev/null 2>&1 || { apt-get update -qq && apt-get install -y certbot >/dev/null 2>&1; }
  command -v certbot >/dev/null || die "certbot install failed. Try:  sudo apt-get update && sudo apt-get install -y certbot"
fi
echo "  all prerequisites present."

mkdir -p "$CERT_CONFIG" "$CERT_WORK" "$CERT_LOGS" "$WEBROOT"

# ---------------- 2. domain + Let's Encrypt email ----------------
if [ -f "$ENV_FILE" ]; then
  EXISTING_BASE_URL="$(grep -E '^BASE_URL=' "$ENV_FILE" | head -1 | cut -d= -f2- || true)"
  EXISTING_BASE_URL="${EXISTING_BASE_URL#http://}"
  EXISTING_BASE_URL="${EXISTING_BASE_URL#https://}"
  EXISTING_BASE_URL="${EXISTING_BASE_URL%%/*}"
else
  EXISTING_BASE_URL=""
fi

say "Domain configuration"
DOMAIN="${DOMAIN:-$(prompt 'Domain name (A record must point to this server)' "$EXISTING_BASE_URL" | tr '[:upper:]' '[:lower:]')}"
DOMAIN="${DOMAIN#http://}"; DOMAIN="${DOMAIN#https://}"; DOMAIN="${DOMAIN%%/*}"
[[ "$DOMAIN" =~ ^([a-z0-9]([a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,}$ ]] || die "Invalid domain name: $DOMAIN"

if [ -f "$ENV_FILE" ]; then
  ENV_LE_EMAIL="$(grep -E '^LETSENCRYPT_EMAIL=' "$ENV_FILE" | head -1 | cut -d= -f2- || true)"
else
  ENV_LE_EMAIL=""
fi
LE_EMAIL="${LETSENCRYPT_EMAIL:-$(prompt 'Let'\''s Encrypt email (renewal notices)' "$ENV_LE_EMAIL")}"
[[ "$LE_EMAIL" =~ ^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$ ]] || die "A valid email is required for Let's Encrypt: $LE_EMAIL"

# ---------------- 3. .env configuration ----------------
say "Configuring .env"
if [ ! -f "$ENV_FILE" ]; then
  cp "$ROOT/.env.example" "$ENV_FILE"
  echo "  created .env from .env.example"
fi

# shellcheck disable=SC1090,SC1091
set -a; source "$ENV_FILE" 2>/dev/null || true; set +a

if [ "${SECRET_KEY:-}" = "change-me-in-production" ] || [ -z "${SECRET_KEY:-}" ]; then
  upsert_env SECRET_KEY "$(openssl rand -hex 32)"
  echo "  generated a random SECRET_KEY"
fi
if [ -z "${POSTGRES_PASSWORD:-}" ] || [ "${POSTGRES_PASSWORD:-}" = "outreach-change-me" ]; then
  upsert_env POSTGRES_PASSWORD "$(openssl rand -hex 16)"
  echo "  generated a random POSTGRES_PASSWORD"
fi
upsert_env BASE_URL "https://$DOMAIN"
upsert_env CORS_ORIGINS "https://$DOMAIN"
upsert_env GOOGLE_REDIRECT_URI "https://$DOMAIN/api/integrations/gmail/oauth/callback"
upsert_env LETSENCRYPT_EMAIL "$LE_EMAIL"
echo "  BASE_URL / CORS_ORIGINS / GOOGLE_REDIRECT_URI -> https://$DOMAIN"

# ---------------- 4. optional initial-admin bootstrap ----------------
# Done BEFORE the first `compose up` so the admin is created on API first boot.
if [ "${NO_PROMPT:-0}" != "1" ] && [ -z "${INITIAL_ADMIN_USERNAME:-}" ]; then
  say "Initial admin account (optional)"
  ans="$(prompt 'Create an admin account now? The setup wizard can do it later' 'N')"
  case "$ans" in y|Y|yes|YES)
    u="$(prompt '  Admin username' 'admin')"
    read -rsp '  Admin password (>= 8 characters): ' pw || true; echo
    [ "${#pw}" -ge 8 ] || die "Admin password must be at least 8 characters"
    em="$(prompt '  Admin email' '')"
    [ -n "$em" ] || die "Admin email is required"
    upsert_env INITIAL_ADMIN_USERNAME "$u"
    upsert_env INITIAL_ADMIN_PASSWORD "$pw"
    upsert_env INITIAL_ADMIN_EMAIL "$em"
    echo "  admin credentials written to .env (created on first boot)"
  esac
fi

# ---------------- 5. DNS sanity check ----------------
if [ "${SKIP_DNS_CHECK:-0}" != "1" ]; then
  say "Verifying DNS for $DOMAIN"
  PUBLIC_IP="$(curl -fsS --max-time 10 https://api.ipify.org 2>/dev/null || true)"
  DOMAIN_IP="$(getent ahosts "$DOMAIN" | awk 'NR==1 {print $1}' 2>/dev/null || true)"
  if [ -n "$PUBLIC_IP" ] && [ -n "$DOMAIN_IP" ]; then
    if [ "$PUBLIC_IP" != "$DOMAIN_IP" ]; then
      warn "$DOMAIN resolves to $DOMAIN_IP but this server's public IP is $PUBLIC_IP."
      warn "The certificate issuance will fail until DNS is fixed."
      [ "${NO_PROMPT:-0}" = "1" ] || { ans="$(prompt 'Continue anyway?' 'N')"; case "$ans" in y|Y|yes|YES) ;; *) die "Fix the A record first, then re-run this installer.";; esac; }
    else
      echo "  OK - $DOMAIN -> $DOMAIN_IP"
    fi
  elif [ -n "$DOMAIN_IP" ]; then
    echo "  (could not determine this server's public IP - skipping IP comparison)"
  else
    warn "$DOMAIN does not resolve to any address. Fix DNS or re-run with SKIP_DNS_CHECK=1."
    [ "${NO_PROMPT:-0}" = "1" ] || { ans="$(prompt 'Continue anyway?' 'N')"; case "$ans" in y|Y|yes|YES) ;; *) die "Fix the A record first, then re-run this installer.";; esac; }
  fi
fi

# ---------------- 6. start the stack (HTTP) ----------------
say "Starting services (first build can take several minutes)"
if [ "${SKIP_BUILD:-0}" = "1" ]; then
  docker compose up -d
else
  docker compose up -d --build
fi

# ---------------- 7. wait for API readiness ----------------
if [ "${NO_WAIT:-0}" != "1" ]; then
  say "Waiting for the API to be ready"
  API_READY=0
  for _ in $(seq 1 60); do
    if curl -fsS "http://127.0.0.1:${HTTP_PORT:-80}/ready" >/dev/null 2>&1; then API_READY=1; break; fi
    sleep 5
  done
  [ "$API_READY" = "1" ] || { echo "  still starting - check:  docker compose logs api"; exit 1; }
  echo "  API is ready."
fi

# ---------------- 8. Let's Encrypt certificate ----------------
CERT_LIVE="$CERT_CONFIG/live/$DOMAIN"
if [ -f "$CERT_LIVE/fullchain.pem" ] && [ -f "$CERT_LIVE/privkey.pem" ]; then
  say "Certificate for $DOMAIN already exists - skipping issuance"
else
  say "Issuing Let's Encrypt certificate for $DOMAIN (HTTP-01 challenge)"
  echo "  This requires ports 80 and 443 reachable from the internet..."
  if ! certbot certonly --webroot --non-interactive --agree-tos -m "$LE_EMAIL" \
        -d "$DOMAIN" -w "$WEBROOT" \
        --config-dir "$CERT_CONFIG" --work-dir "$CERT_WORK" --logs-dir "$CERT_LOGS"; then
    echo
    warn "Certificate issuance failed. Common causes:"
    warn "  - the A record for $DOMAIN does not point to this server"
    warn "  - port 80 is blocked by the firewall / security group"
    warn "  - the challenge files cannot be reached at http://$DOMAIN/.well-known/acme-challenge/"
    echo
    die "The stack is still running at http://$DOMAIN - fix the issue and re-run this installer."
  fi
  echo "  certificate issued."
fi

# ---------------- 9. enable HTTPS ----------------
say "Enabling HTTPS"
sed "s|__DOMAIN__|$DOMAIN|g" "$SSL_TPL" > "$SSL_CONF"
echo "  wrote $SSL_CONF"
if ! docker compose exec -T reverse-proxy nginx -s reload >/dev/null 2>&1 \
   && ! docker compose kill -s HUP reverse-proxy >/dev/null 2>&1; then
  die "Could not reload the reverse proxy - check:  docker compose logs reverse-proxy"
fi
echo "  reverse proxy reloaded with the TLS listener."

if [ "${NO_WAIT:-0}" != "1" ]; then
  HTTPS_READY=0
  for _ in $(seq 1 36); do
    if curl -fsS --max-time 10 "https://$DOMAIN/ready" >/dev/null 2>&1; then HTTPS_READY=1; break; fi
    sleep 5
  done
  [ "$HTTPS_READY" = "1" ] || die "https://$DOMAIN did not become ready - check:  docker compose logs reverse-proxy"
  echo "  https://$DOMAIN is serving requests."
fi

# ---------------- 10. automatic renewal ----------------
if [ "${SKIP_RENEWAL:-0}" != "1" ]; then
  say "Installing automatic certificate renewal"
  if [ -d /run/systemd/system ] && command -v systemctl >/dev/null 2>&1; then
    cat > /etc/systemd/system/avop-renew.service <<EOF
[Unit]
Description=Renew Let's Encrypt certificates for the AI Vendor Outreach Platform
After=network-online.target docker.service
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=$ROOT/scripts/renew-cert.sh
EOF
    cat > /etc/systemd/system/avop-renew.timer <<EOF
[Unit]
Description=Daily Let's Encrypt renewal for the AI Vendor Outreach Platform

[Timer]
OnCalendar=*-*-* 03:17:00
Persistent=true
RandomizedDelaySec=900

[Install]
WantedBy=timers.target
EOF
    systemctl daemon-reload >/dev/null 2>&1 || true
    systemctl enable --now avop-renew.timer >/dev/null 2>&1 || true
    echo "  systemd timer 'avop-renew' installed (daily at 03:17)."
  elif command -v crontab >/dev/null 2>&1; then
    ( crontab -l 2>/dev/null | grep -v 'avop-renew-certs' || true
      echo "17 3 * * * $ROOT/scripts/renew-cert.sh >/dev/null 2>&1 # avop-renew-certs" ) | crontab -
    echo "  cron job installed (daily at 03:17)."
  else
    warn "No systemd or cron available - renew manually:  sudo bash scripts/renew-cert.sh"
  fi
fi

# ---------------- 11. summary ----------------
say "Installation complete"
echo
echo "  Your platform is live at:"
echo
echo "      https://$DOMAIN"
echo
echo "  Health/probes:  https://$DOMAIN/health   https://$DOMAIN/ready"
echo
echo "  Next steps - the rest is configured in the web panel (no SSH needed):"
echo "    - Log in with the admin account you created (or complete the setup wizard)"
echo "    - Settings -> AI       : paste your OpenRouter API key"
echo "    - Settings -> Email    : connect Gmail (OAuth) or SMTP (Microsoft 365/Outlook)"
echo "    - Settings -> Telegram : paste your bot token and chat id"
echo
echo "  Certificate renewal is automatic (daily 03:17). Manual:  sudo bash scripts/renew-cert.sh"
echo "  Useful commands:  bash scripts/status.sh   |   restore/backup in scripts/"
