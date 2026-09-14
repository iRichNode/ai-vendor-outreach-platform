#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# AI Vendor Outreach Platform - status
#   bash scripts/status.sh
# Prints service table + health/readiness/setup status.
# ---------------------------------------------------------------------------
set -uo pipefail
cd "$(dirname "$0")/.."

command -v docker >/dev/null || { echo "docker not found" >&2; exit 1; }

echo "==> docker compose ps"
docker compose ps || true
echo

PORT="${HTTP_PORT:-80}"
for probe in health ready; do
  CODE="$(curl -sS -o /tmp/avop_probe.json -w '%{http_code}' "http://127.0.0.1:${PORT}/${probe}" 2>/dev/null || echo "000")"
  printf '%-8s -> HTTP %s  %s\n' "/$probe" "$CODE" "$(head -c 120 /tmp/avop_probe.json 2>/dev/null)"
done

SETUP="$(curl -sS "http://127.0.0.1:${PORT}/api/setup/status" 2>/dev/null || echo '{}')"
printf 'setup status : %s\n' "$(printf '%s' "$SETUP" | grep -o '"setup_required": *[a-z]*' | head -1 || echo "unknown")"