#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# AI Vendor Outreach Platform - Ubuntu VPS installer
#
#   sudo bash scripts/install.sh
#
# What it does (all non-destructive):
#   1. Validates prerequisites  (git, docker, docker compose plugin, openssl)
#   2. Validates configuration  (creates .env from .env.example if missing,
#      generates SECRET_KEY when it is still the placeholder)
#   3. Starts services          (docker compose up -d --build)
#   4. Runs migrations          (alembic upgrade head runs inside the api
#      container on first healthy start - idempotent)
#   5. Initializes application  (waits for /ready; reports setup-wizard status)
#   6. Reports status           (service table + health probes)
#
# Environment overrides:
#   SKIP_BUILD=1        start without rebuilding images
#   NO_PROMPT=1         do not ask before starting (CI-friendly)
# ---------------------------------------------------------------------------
set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$(pwd)"

say() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
die() { printf '\033[1;31mERROR: %s\033[0m\n' "$*" >&2; exit 1; }

# ---------------- 1. prerequisites ----------------
say "Validating prerequisites"
command -v git        >/dev/null || die "git is required:  sudo apt install -y git"
command -v openssl    >/dev/null || die "openssl is required:  sudo apt install -y openssl"
command -v docker     >/dev/null || die "docker is required:  https://docs.docker.com/engine/install/ubuntu/"
docker compose version >/dev/null 2>&1 || die "docker compose plugin is required:  sudo apt install -y docker-compose-plugin"

# ---------------- 2. configuration ----------------
say "Validating configuration"
if [ ! -f "$ROOT/.env" ]; then
  cp "$ROOT/.env.example" "$ROOT/.env"
  echo "  created .env from .env.example - edit it before going live."
else
  echo "  .env already present - keeping it."
fi

# shellcheck disable=SC1091
set -a; source "$ROOT/.env" 2>/dev/null || true; set +a

if [ "${SECRET_KEY:-}" = "change-me-in-production" ] || [ -z "${SECRET_KEY:-}" ]; then
  NEW_SECRET="$(openssl rand -hex 32)"
  sed -i.bak "s/^SECRET_KEY=.*/SECRET_KEY=$NEW_SECRET/" "$ROOT/.env"
  rm -f "$ROOT/.env.bak"
  echo "  generated a random SECRET_KEY in .env"
fi

# shellcheck disable=SC1091
set -a; source "$ROOT/.env"; set +a

[ -n "${SECRET_KEY:-}" ] || die "SECRET_KEY must be set in .env"

# ---------------- 3. start services ----------------
say "Starting services (this can take several minutes on first build)"
if [ "${SKIP_BUILD:-0}" = "1" ]; then
  docker compose up -d
else
  docker compose up -d --build
fi

# ---------------- 4. migrations ----------------
say "Waiting for API readiness (auto-migration runs inside the container)"
API_READY=0
for _ in $(seq 1 60); do
  if curl -fsS "http://127.0.0.1:${HTTP_PORT:-80}/ready" >/dev/null 2>&1; then
    API_READY=1; break
  fi
  sleep 5
done
[ "$API_READY" = "1" ] || { echo "  still starting - check: docker compose logs api"; exit 1; }
echo "  API is ready."

# ---------------- 5. initialize application ----------------
say "Initializing application"
SETUP_STATUS="$(curl -fsS "http://127.0.0.1:${HTTP_PORT:-80}/api/setup/status" 2>/dev/null || echo '{}')"
if printf '%s' "$SETUP_STATUS" | grep -q '"setup_required": *true'; then
  echo "  First run: open http://$(hostname -I 2>/dev/null | awk '{print $1}'):${HTTP_PORT:-80} and complete the setup wizard."
  echo "  (Or pre-seed INITIAL_ADMIN_USERNAME/PASSWORD/EMAIL in .env and restart the api container.)"
elif printf '%s' "$SETUP_STATUS" | grep -q '"setup_required": *false'; then
  echo "  Admin account already exists - setup complete."
else
  echo "  Could not determine setup state (API may still be warm). Re-run: bash scripts/status.sh"
fi

# ---------------- 6. status ----------------
say "Status"
docker compose ps
echo
echo "  API /health : $(curl -sS -o /dev/null -w '%{http_code}' "http://127.0.0.1:${HTTP_PORT:-80}/health")"
echo "  API /ready  : $(curl -sS -o /dev/null -w '%{http_code}' "http://127.0.0.1:${HTTP_PORT:-80}/ready")"
echo
echo "Installation finished. Next: configure HTTPS/Gmail/AI - see docs/deployment.md"