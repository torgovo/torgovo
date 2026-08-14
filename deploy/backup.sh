#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# Torgovo Database Backup
# =============================================================================
# Usage: ./deploy/backup.sh [--s3] [--retain N]
#
# Dependencies: pg_dump, gzip (optional: aws cli for S3)
#
# Environment variables (from .env or set manually):
#   DB_NAME, DB_USER, DB_PASSWORD, DB_HOST, DB_PORT
#   BACKUP_DIR (default: /var/backups/torgovo)
#   AWS_S3_BUCKET (optional, for S3 upload)
#   RETENTION_DAYS (default: 30)
# =============================================================================

BACKUP_DIR="${BACKUP_DIR:-/var/backups/torgovo}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
FILENAME="torgovo_db_${TIMESTAMP}.sql.gz"
BACKUP_PATH="${BACKUP_DIR}/${FILENAME}"

if [ -f .env ]; then
    set -a; source .env; set +a
fi

mkdir -p "${BACKUP_DIR}"

echo "=== Dumping database ${DB_NAME} -> ${BACKUP_PATH} ==="
PGPASSWORD="${DB_PASSWORD}" pg_dump \
    -h "${DB_HOST:-127.0.0.1}" \
    -p "${DB_PORT:-5432}" \
    -U "${DB_USER:-postgres}" \
    -d "${DB_NAME}" \
    --no-owner \
    --no-acl \
    --format=custom \
    | gzip > "${BACKUP_PATH}"

echo "   Size: $(du -h "${BACKUP_PATH}" | cut -f1)"

if [ "${1:-}" = "--s3" ] && [ -n "${AWS_S3_BUCKET:-}" ]; then
    echo "=== Uploading to s3://${AWS_S3_BUCKET}/ ==="
    aws s3 cp "${BACKUP_PATH}" "s3://${AWS_S3_BUCKET}/db/"
    echo "   Upload complete"
fi

echo "=== Cleaning backups older than ${RETENTION_DAYS} days ==="
find "${BACKUP_DIR}" -name "torgovo_db_*.sql.gz" -type f -mtime "+${RETENTION_DAYS}" -delete
echo "   Done"

echo "=== Backup complete: ${FILENAME} ==="
