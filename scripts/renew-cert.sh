#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# AI Vendor Outreach Platform - renew Let's Encrypt certificates and reload
# the reverse proxy so the renewed certificates are picked up.
#
#   sudo bash scripts/renew-cert.sh
#
# This is what the 'avop-renew' systemd timer (or cron fallback) runs daily.
# Uses the same certbot directories as scripts/install.sh.
# ---------------------------------------------------------------------------
set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$(pwd)"
CERT_CONFIG="$ROOT/infra/certs/etc/letsencrypt"
CERT_WORK="$ROOT/infra/certs/work"
CERT_LOGS="$ROOT/infra/certs/logs"
WEBROOT="$ROOT/infra/certs/www"

command -v certbot >/dev/null 2>&1 || { echo "certbot not found: sudo apt install -y certbot" >&2; exit 1; }

echo "==> certbot renew"
certbot renew \
  --config-dir "$CERT_CONFIG" \
  --work-dir "$CERT_WORK" \
  --logs-dir "$CERT_LOGS" \
  --webroot -w "$WEBROOT" \
  --quiet

echo "==> reloading reverse proxy"
if ! docker compose exec -T reverse-proxy nginx -s reload >/dev/null 2>&1 \
   && ! docker compose kill -s HUP reverse-proxy >/dev/null 2>&1; then
  echo "Could not reload the reverse proxy - check: docker compose logs reverse-proxy" >&2
  exit 1
fi

echo "done."
