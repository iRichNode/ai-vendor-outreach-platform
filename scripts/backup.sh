#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# AI Vendor Outreach Platform - backup
#
#   scripts/backup.sh [--keep N]
#
# Backs up:
#   * PostgreSQL database  -> backups/ai_vendor_outreach_<ts>.dump.gz
#   * App data volume      -> backups/ai_vendor_outreach_<ts>.appdata.tar.gz
#     (contains the Gmail OAuth token and any GMAIL_TOKEN_FILE artifacts)
#
# Keeps the 7 most recent backups by default (override with --keep N).
# Restore: scripts/restore.sh backups/ai_vendor_outreach_<ts>.dump.gz
# ---------------------------------------------------------------------------
set -euo pipefail
cd "$(dirname "$0")/.."

KEEP=7
[ "${1:-}" = "--keep" ] && { KEEP="$2"; shift 2; }

command -v docker >/dev/null || { echo "docker not found" >&2; exit 1; }
docker compose ps >/dev/null 2>&1 || { echo "stack is not running" >&2; exit 1; }

mkdir -p backups
TS="$(date +%Y%m%d_%H%M%S)"
DB_DUMP="backups/ai_vendor_outreach_${TS}.dump.gz"
DATA_TAR="backups/ai_vendor_outreach_${TS}.appdata.tar.gz"

echo "==> Backing up database -> $DB_DUMP"
docker compose exec -T postgres pg_dump -U "${POSTGRES_USER:-outreach}" -d "${POSTGRES_DB:-outreach}" --format=custom | gzip > "$DB_DUMP"

echo "==> Backing up app data -> $DATA_TAR"
if docker compose exec -T api sh -c 'test -d /srv/app/data && tar -czf /tmp/appdata.tar.gz -C /srv/app/data . 2>/dev/null' >/dev/null 2>&1; then
  docker compose cp api:/tmp/appdata.tar.gz "$DATA_TAR" >/dev/null 2>&1 || true
  docker compose exec -T api rm -f /tmp/appdata.tar.gz >/dev/null 2>&1 || true
  [ -s "$DATA_TAR" ] || rm -f "$DATA_TAR"
else
  echo "  (no app data volume mounted or empty - continuing)"
fi

echo "==> Pruning: keeping the newest $KEEP backup timestamps"
# Each backup timestamp produces two files (<ts>.dump.gz and <ts>.appdata.tar.gz).
ls -1t backups/ai_vendor_outreach_*.dump.gz 2>/dev/null \
  | tail -n +$((KEEP + 1)) \
  | while read -r f; do
      ts="${f#backups/ai_vendor_outreach_}"; ts="${ts%.dump.gz}"
      rm -f "backups/ai_vendor_outreach_${ts}.dump.gz" "backups/ai_vendor_outreach_${ts}.appdata.tar.gz"
    done

echo
echo "Backup complete:"
ls -lh backups/ | tail -n +2 | column -t || true
echo "Copy the backups/ directory off-site (scp/rsync/object storage)."