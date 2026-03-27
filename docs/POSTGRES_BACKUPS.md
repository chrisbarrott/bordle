# Postgres Backup Runbook

This project includes an automated daily Postgres backup workflow that runs in GitHub Actions.

Backups are stored for free in a dedicated git branch in this repository.

## What Is Included

- Daily scheduled workflow: `.github/workflows/daily-postgres-backup.yml`
- Backup script: `scripts/create_postgres_backup.sh`
- Restore script: `scripts/restore_postgres_backup.sh`

Backups are generated using `pg_dump` custom format (`.dump`) and accompanied by a SHA256 checksum file.

## Storage Modes

- Primary: push daily dumps to backup branch (default `backup-dumps`)
- Short-term: GitHub Action artifacts (7 days)

## 1. Configure GitHub Secrets

Add these repository secrets:

- `BACKUP_DATABASE_URL` (required)

Backups are produced and stored in the backup branch plus GitHub artifacts for 7 days.

Optional repository variables (Settings -> Secrets and variables -> Actions -> Variables):

- `BACKUP_GIT_BRANCH` (default: `backup-dumps`)
- `BACKUP_GIT_RETENTION_COUNT` (default: `7`)

## 2. Schedule

The workflow runs daily at `03:15 UTC` and can also be triggered manually via `workflow_dispatch`.

## 3. Retention

Local cleanup in the workflow runner is controlled by `BACKUP_RETENTION_DAYS` (currently `7`).

Backup branch retention is controlled by `BACKUP_GIT_RETENTION_COUNT` (default `7` dump files).

Important git-branch caveats:

- Keep dump files under GitHub file limits (hard limit: 100 MB per file).
- Repository history will grow over time.
- Prefer private repos for backups, even if data is non-sensitive.

If you later outgrow git-based storage, add external object storage and lifecycle policies.

## 4. Restore Procedure

Restore a backup into a target database:

```bash
bash scripts/restore_postgres_backup.sh backups/bordle-postgres-YYYYMMDDTHHMMSSZ.dump "$TARGET_DATABASE_URL"
```

Or set `DATABASE_URL` and omit the second argument:

```bash
export DATABASE_URL="postgres://..."
bash scripts/restore_postgres_backup.sh backups/bordle-postgres-YYYYMMDDTHHMMSSZ.dump
```

## 5. Manual Backup Run (Optional)

```bash
export DATABASE_URL="postgres://..."
bash scripts/create_postgres_backup.sh
```

Optional env vars:

- `BACKUP_DIR` (default: `backups`)
- `BACKUP_PREFIX` (default: `bordle-postgres`)
- `BACKUP_RETENTION_DAYS` (default: `7`)

## 6. Weekly Restore Drill (Recommended)

At least once a week:

- Restore the latest backup to a temporary database
- Verify key tables and row counts
- Run basic app smoke tests against the restored DB
- Record restore time and any failures
