#!/usr/bin/env bash
# =============================================================================
# PostgreSQL Restore Script for QBMigration
# =============================================================================
# Restores an encrypted PostgreSQL backup created by backup-db.sh.
#
# Usage:
#   ./scripts/restore-db.sh <backup-file>
#   ./scripts/restore-db.sh s3://bucket/backups/postgres/qbmigration_20260211T120000Z.sql.gz.enc
#
# Environment variables (set in .env or export):
#   POSTGRES_HOST       (default: localhost)
#   POSTGRES_PORT       (default: 5432)
#   POSTGRES_USER       (required)
#   POSTGRES_PASSWORD   (required)
#   POSTGRES_DB         (default: qbmigration)
#   BACKUP_ENCRYPTION_KEY (required — same key used during backup)
#   AWS_REGION          (default: ca-central-1)
# =============================================================================
set -euo pipefail

# Load .env if present
if [ -f "$(dirname "$0")/../.env" ]; then
    # shellcheck disable=SC1091
    set -a; source "$(dirname "$0")/../.env"; set +a
fi

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
POSTGRES_HOST="${POSTGRES_HOST:-localhost}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_USER="${POSTGRES_USER:?ERROR: POSTGRES_USER is required}"
POSTGRES_DB="${POSTGRES_DB:-qbmigration}"

if [ $# -lt 1 ]; then
    echo "Usage: $0 <backup-file-or-s3-uri>" >&2
    exit 1
fi

BACKUP_SOURCE="$1"

if [ -z "${POSTGRES_PASSWORD:-}" ]; then
    echo "ERROR: POSTGRES_PASSWORD is required" >&2
    exit 1
fi

if [ -z "${BACKUP_ENCRYPTION_KEY:-}" ]; then
    echo "ERROR: BACKUP_ENCRYPTION_KEY is required to decrypt backups" >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Download from S3 if needed
# ---------------------------------------------------------------------------
BACKUP_FILE="$BACKUP_SOURCE"
TEMP_FILE=""
if [[ "$BACKUP_SOURCE" == s3://* ]]; then
    TEMP_FILE="$(mktemp /tmp/qbmigration_restore_XXXXXX.sql.gz.enc)"
    echo "[$(date -u +%FT%TZ)] Downloading from ${BACKUP_SOURCE}..."
    aws s3 cp "$BACKUP_SOURCE" "$TEMP_FILE" --region "${AWS_REGION:-ca-central-1}"
    BACKUP_FILE="$TEMP_FILE"
fi

if [ ! -f "$BACKUP_FILE" ]; then
    echo "ERROR: Backup file not found: ${BACKUP_FILE}" >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Safety confirmation
# ---------------------------------------------------------------------------
echo ""
echo "=== DESTRUCTIVE OPERATION ==="
echo "This will DROP and recreate the database: ${POSTGRES_DB}"
echo "Host: ${POSTGRES_HOST}:${POSTGRES_PORT}"
echo "Backup: ${BACKUP_SOURCE}"
echo ""
read -rp "Type 'RESTORE' to confirm: " CONFIRM
if [ "$CONFIRM" != "RESTORE" ]; then
    echo "Aborted."
    [ -n "$TEMP_FILE" ] && rm -f "$TEMP_FILE"
    exit 1
fi

echo "[$(date -u +%FT%TZ)] Starting restore of ${POSTGRES_DB}..."

# ---------------------------------------------------------------------------
# Drop and recreate database
# ---------------------------------------------------------------------------
PGPASSWORD="$POSTGRES_PASSWORD" psql \
    -h "$POSTGRES_HOST" \
    -p "$POSTGRES_PORT" \
    -U "$POSTGRES_USER" \
    -d postgres \
    -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '${POSTGRES_DB}' AND pid <> pg_backend_pid();" \
    2>/dev/null || true

PGPASSWORD="$POSTGRES_PASSWORD" psql \
    -h "$POSTGRES_HOST" \
    -p "$POSTGRES_PORT" \
    -U "$POSTGRES_USER" \
    -d postgres \
    -c "DROP DATABASE IF EXISTS ${POSTGRES_DB};"

PGPASSWORD="$POSTGRES_PASSWORD" psql \
    -h "$POSTGRES_HOST" \
    -p "$POSTGRES_PORT" \
    -U "$POSTGRES_USER" \
    -d postgres \
    -c "CREATE DATABASE ${POSTGRES_DB} OWNER ${POSTGRES_USER};"

# ---------------------------------------------------------------------------
# Decrypt → decompress → restore
# ---------------------------------------------------------------------------
openssl enc -aes-256-cbc -d -salt -pbkdf2 -iter 100000 \
    -pass "pass:${BACKUP_ENCRYPTION_KEY}" \
    -in "$BACKUP_FILE" \
    | gunzip \
    | PGPASSWORD="$POSTGRES_PASSWORD" psql \
        -h "$POSTGRES_HOST" \
        -p "$POSTGRES_PORT" \
        -U "$POSTGRES_USER" \
        -d "$POSTGRES_DB" \
        --single-transaction \
        --set ON_ERROR_STOP=on

# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------
[ -n "$TEMP_FILE" ] && rm -f "$TEMP_FILE"

echo "[$(date -u +%FT%TZ)] Restore complete. Database: ${POSTGRES_DB}"
echo ""
echo "Next steps:"
echo "  1. Run 'flask db upgrade' to apply any pending Alembic migrations"
echo "  2. Verify the application starts correctly"
echo "  3. Run a health check: curl http://localhost:5000/health"
