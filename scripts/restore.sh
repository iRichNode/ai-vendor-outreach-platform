#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# AI Vendor Outreach Platform - restore
#
#   scripts/restore.sh backups/ai_vendor_outreach_<ts>.dump.gz
#
# Restores the PostgreSQL database from a backup produced by backup.sh.
# DESTRUCTIVE: replaces the current database contents.
# ---------------------------------------------------------------------------
set -euo pipefail
cd "$(dirname "$0")/.."

DB_DUMP="${1:?usage: scripts/restore.sh backups/ai_vendor_outreach_<ts>.dump.gz}"
[ -f "$DB_DUMP" ] || { echo "backup file not found: $DB_DUMP" >&2; exit 1; }

command -v docker >/dev/null || { echo "docker not found" >&2; exit 1; }
docker compose ps >/dev/null 2>&1 || { echo "stack is not running: docker compose up -d first" >&2; exit 1; }

echo "This will REPLACE the current database with the backup."
read -r -p "Type 'restore' to continue: " CONFIRM
[ "$CONFIRM" = "restore" ] || { echo "Aborted."; exit 1; }

echo "==> Restoring database from $DB_DUMP"

# Drop and recreate the schema so the dump applies cleanly.
docker compose exec -T postgres psql -U "${POSTGRES_USER:-outreach}" -d "${POSTGRES_DB:-outreach}" \
  -c 'DROP SCHEMA public CASCADE; CREATE SCHEMA public;' >/dev/null

# --clean --if-exists clears objects; schema was already recreated.
gzip -dc "$DB_DUMP" | docker compose exec -T postgres pg_restore \
  -U "${POSTGRES_USER:-outreach}" -d "${POSTGRES_DB:-outreach}" \
  --no-owner --role="${POSTGRES_USER:-outreach}" --clean --if-exists

echo "==> Restarting API/worker/scheduler so they see the restored state"
docker compose restart api worker scheduler >/dev/null

echo "Restore complete. Verify with: bash scripts/status.sh"