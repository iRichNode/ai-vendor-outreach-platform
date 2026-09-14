# Backup & restore

## 1. What is backed up

1. **PostgreSQL database** — every table: users, campaigns, vendors,
   conversations, meetings, the `scheduled_jobs` queue, settings, audit logs.
   Format: `pg_dump --format=custom` gzip-compressed
   (`backups/ai_vendor_outreach_<ts>.dump.gz`). Custom format restores with
   `pg_restore` and supports selective restores.
2. **App data volume** (`appdata`) — the Gmail OAuth token file
   (`gmail_token.json`) and any other long-lived files under
   `/srv/app/data` in the api/worker/scheduler containers
   (`backups/ai_vendor_outreach_<ts>.appdata.tar.gz`).

Not backed up (recreatable): Docker images, Redis cache, `pgdata` volume
(Postgres restores from the dump create it fresh).

## 2. Take a backup

```bash
sudo bash scripts/backup.sh            # keep the 7 most recent timestamps
sudo bash scripts/backup.sh --keep 14  # keep more
```

The script requires the Compose stack to be running (`docker compose ps`).
Artifacts land in `backups/` at the repository root; each timestamp produces a
database dump plus an appdata archive, and old timestamps are pruned beyond
`--keep`.

## 3. Automate nightly backups

```bash
crontab -e
```

```cron
# 3:05 am nightly; logs to syslog; complains by mail on failure (MAILTO)
5 3 * * * cd /opt/ai-vendor-outreach-platform && bash scripts/backup.sh >> /var/log/outreach-backup.log 2>&1
```

Copy the `backups/` directory off-site (scp/rsync/object storage) — a backup
on the same disk as the database protects against nothing.

## 4. Restore

```bash
sudo bash scripts/restore.sh backups/ai_vendor_outreach_20260914_030500.dump.gz
```

`scripts/restore.sh`:

1. Stops the `api`, `worker` and `scheduler` services (they hold DB
   connections/locks on the schema).
2. Recreates an empty database.
3. Runs `pg_restore --clean --if-exists` from the dump.
4. Replaces the app-data files from the matching `.appdata.tar.gz` (if the
   sibling archive exists).
5. Restarts the services and prints status.

> Restores replace current state — run them on the exact database name in
> `.env`, and only when you intend to roll back.

## 5. Validation / testing

- **Monthly test restore** on a scratch database to prove the dump is restorable
  (dumps silently rot). Example:
  ```bash
  docker compose exec -T postgres createdb -U outreach outreach_restore_test
  docker compose exec -T postgres pg_restore -U outreach -d outreach_restore_test --no-owner backups/ai_vendor_outreach_<ts>.dump.gz
  docker compose exec -T postgres psql -U outreach -d outreach_restore_test -c 'select count(*) from vendors;'
  docker compose exec -T postgres dropdb -U outreach outreach_restore_test
  ```
- Spot-check the queue table after restore:
  `select status, count(*) from scheduled_jobs group by status;`
- Verify Gmail is still connected after restoring `appdata` (`/integrations/status`).