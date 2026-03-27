#!/usr/bin/env bash

set -euo pipefail

if ! command -v pg_restore >/dev/null 2>&1; then
  echo "Error: pg_restore is not installed or not on PATH" >&2
  exit 1
fi

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <backup.dump> [target_database_url]" >&2
  exit 1
fi

BACKUP_FILE="$1"
TARGET_DATABASE_URL="${2:-${DATABASE_URL:-}}"

if [[ ! -f "$BACKUP_FILE" ]]; then
  echo "Error: Backup file not found: $BACKUP_FILE" >&2
  exit 1
fi

if [[ -z "$TARGET_DATABASE_URL" ]]; then
  echo "Error: target_database_url argument or DATABASE_URL env var is required" >&2
  exit 1
fi

echo "Restoring backup ${BACKUP_FILE} into target database"
pg_restore \
  --dbname "$TARGET_DATABASE_URL" \
  --clean \
  --if-exists \
  --no-owner \
  --no-privileges \
  "$BACKUP_FILE"

echo "Restore completed successfully"
