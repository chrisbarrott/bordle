#!/usr/bin/env bash

set -euo pipefail

if ! command -v pg_dump >/dev/null 2>&1; then
  echo "Error: pg_dump is not installed or not on PATH" >&2
  exit 1
fi

if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "Error: DATABASE_URL environment variable is required" >&2
  exit 1
fi

BACKUP_DIR="${BACKUP_DIR:-backups}"
BACKUP_PREFIX="${BACKUP_PREFIX:-bordle-postgres}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-7}"

mkdir -p "$BACKUP_DIR"

TIMESTAMP="$(date -u +"%Y%m%dT%H%M%SZ")"
BACKUP_FILENAME="${BACKUP_PREFIX}-${TIMESTAMP}.dump"
BACKUP_PATH="${BACKUP_DIR}/${BACKUP_FILENAME}"

echo "Creating Postgres backup: ${BACKUP_PATH}"
pg_dump \
  --dbname "$DATABASE_URL" \
  --format=custom \
  --no-owner \
  --no-privileges \
  --compress=9 \
  --file "$BACKUP_PATH"

if command -v sha256sum >/dev/null 2>&1; then
  sha256sum "$BACKUP_PATH" > "${BACKUP_PATH}.sha256"
elif command -v shasum >/dev/null 2>&1; then
  shasum -a 256 "$BACKUP_PATH" > "${BACKUP_PATH}.sha256"
fi

if [[ "$RETENTION_DAYS" =~ ^[0-9]+$ ]] && [[ "$RETENTION_DAYS" -gt 0 ]]; then
  find "$BACKUP_DIR" -type f \( -name "${BACKUP_PREFIX}-*.dump" -o -name "${BACKUP_PREFIX}-*.dump.sha256" \) -mtime "+${RETENTION_DAYS}" -delete
fi

echo "Backup created successfully: ${BACKUP_PATH}"

# For GitHub Actions consumers
if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
  echo "backup_file=${BACKUP_PATH}" >> "$GITHUB_OUTPUT"
  echo "backup_filename=${BACKUP_FILENAME}" >> "$GITHUB_OUTPUT"
fi
