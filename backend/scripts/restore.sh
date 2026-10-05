#!/bin/bash
set -euo pipefail

if [ $# -eq 0 ]; then
  echo "Usage: $0 <backup_file.sql.gz>" >&2
  exit 1
fi

BACKUP_FILE="$1"
PGHOST="${DJANGO_DB_HOST:-db}"
PGPORT="${DJANGO_DB_PORT:-5432}"
PGDATABASE="${DJANGO_DB_NAME:-lawyer}"
PGUSER="${DJANGO_DB_USER:-lawyer_app}"
PGPASSWORD="${DJANGO_DB_PASSWORD:-}"

export PGPASSWORD

gunzip -c "$BACKUP_FILE" | psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE"
echo "Backup restored from: ${BACKUP_FILE}"
