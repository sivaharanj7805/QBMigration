#!/usr/bin/env bash
# =============================================================================
# PostgreSQL Backup Script for QBMigration
# =============================================================================
# Creates encrypted, timestamped PostgreSQL backups and uploads to S3.
#
# Usage:
#   ./scripts/backup-db.sh                  # Full backup to local + S3
#   ./scripts/backup-db.sh --local-only     # Skip S3 upload
#   ./scripts/backup-db.sh --s3-only        # Skip local retention
#
# Environment variables (set in .env or export):
#   POSTGRES_HOST       (default: localhost)
#   POSTGRES_PORT       (default: 5432)
#   POSTGRES_USER       (required)
#   POSTGRES_PASSWORD   (required)
#   POSTGRES_DB         (default: qbmigration)
#   BACKUP_DIR          (default: ./backups)
#   BACKUP_RETENTION_DAYS (default: 30)
#   AWS_S3_BUCKET       (required for S3 upload)
#   AWS_REGION          (default: ca-central-1)
#   BACKUP_ENCRYPTION_KEY (required — Fernet key for AES-256 encryption)
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
BACKUP_DIR="${BACKUP_DIR:-$(dirname "$0")/../backups}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-30}"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_FILE="${BACKUP_DIR}/${POSTGRES_DB}_${TIMESTAMP}.sql.gz.enc"
S3_PREFIX="backups/postgres"

LOCAL_ONLY=false
S3_ONLY=false

for arg in "$@"; do
    case "$arg" in
        --local-only) LOCAL_ONLY=true ;;
        --s3-only)    S3_ONLY=true ;;
    esac
done

# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------
if [ -z "${POSTGRES_PASSWORD:-}" ]; then
    echo "ERROR: POSTGRES_PASSWORD is required" >&2
    exit 1
fi

if [ -z "${BACKUP_ENCRYPTION_KEY:-}" ]; then
    echo "ERROR: BACKUP_ENCRYPTION_KEY is required for encrypted backups" >&2
    exit 1
fi

if [ "$S3_ONLY" = false ]; then
    mkdir -p "$BACKUP_DIR"
fi

echo "[$(date -u +%FT%TZ)] Starting backup of ${POSTGRES_DB}..."

# ---------------------------------------------------------------------------
# Dump → compress → encrypt
# ---------------------------------------------------------------------------
PGPASSWORD="$POSTGRES_PASSWORD" pg_dump \
    -h "$POSTGRES_HOST" \
    -p "$POSTGRES_PORT" \
    -U "$POSTGRES_USER" \
    -d "$POSTGRES_DB" \
    --no-owner \
    --no-privileges \
    --format=plain \
    | gzip \
    | openssl enc -aes-256-cbc -salt -pbkdf2 -iter 100000 \
        -pass "pass:${BACKUP_ENCRYPTION_KEY}" \
    > "$BACKUP_FILE"

BACKUP_SIZE=$(stat -c%s "$BACKUP_FILE" 2>/dev/null || stat -f%z "$BACKUP_FILE" 2>/dev/null || echo "unknown")
echo "[$(date -u +%FT%TZ)] Backup created: ${BACKUP_FILE} (${BACKUP_SIZE} bytes)"

# ---------------------------------------------------------------------------
# Upload to S3
# ---------------------------------------------------------------------------
if [ "$LOCAL_ONLY" = false ] && [ -n "${AWS_S3_BUCKET:-}" ]; then
    S3_KEY="${S3_PREFIX}/$(basename "$BACKUP_FILE")"
    echo "[$(date -u +%FT%TZ)] Uploading to s3://${AWS_S3_BUCKET}/${S3_KEY}..."
    aws s3 cp "$BACKUP_FILE" "s3://${AWS_S3_BUCKET}/${S3_KEY}" \
        --region "${AWS_REGION:-ca-central-1}" \
        --storage-class STANDARD_IA \
        --sse AES256
    echo "[$(date -u +%FT%TZ)] S3 upload complete."
elif [ "$LOCAL_ONLY" = false ]; then
    echo "WARNING: AWS_S3_BUCKET not set — skipping S3 upload"
fi

# ---------------------------------------------------------------------------
# Clean up old local backups
# ---------------------------------------------------------------------------
if [ "$S3_ONLY" = false ] && [ -d "$BACKUP_DIR" ]; then
    DELETED=$(find "$BACKUP_DIR" -name "*.sql.gz.enc" -mtime +"$RETENTION_DAYS" -delete -print | wc -l)
    if [ "$DELETED" -gt 0 ]; then
        echo "[$(date -u +%FT%TZ)] Cleaned up ${DELETED} backups older than ${RETENTION_DAYS} days."
    fi
fi

echo "[$(date -u +%FT%TZ)] Backup complete: ${BACKUP_FILE}"
