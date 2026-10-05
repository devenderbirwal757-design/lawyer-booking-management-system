#!/bin/bash
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/backups}"
mkdir -p "$BACKUP_DIR"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
FILENAME="${BACKUP_DIR}/db_backup_${TIMESTAMP}.sql"

PGHOST="${DJANGO_DB_HOST:-db}"
PGPORT="${DJANGO_DB_PORT:-5432}"
PGDATABASE="${DJANGO_DB_NAME:-lawyer}"
PGUSER="${DJANGO_DB_USER:-lawyer_app}"
PGPASSWORD="${DJANGO_DB_PASSWORD:-}"

export PGPASSWORD

pg_dump -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" --clean --if-exists > "$FILENAME"
gzip "$FILENAME"

echo "Backup created: ${FILENAME}.gz"
