#!/usr/bin/env bash
# TimescaleDB audit log backup — runs nightly via cron or Docker scheduled job
# Usage: ./backup/timescaledb_backup.sh
# Requires: pg_dump, aws cli (optional), BACKUP_DIR env var

set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/backups/timescaledb}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-30}"
DB_URL="${DATABASE_URL:?DATABASE_URL must be set}"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="${BACKUP_DIR}/audit_log_${TIMESTAMP}.sql.gz"

mkdir -p "${BACKUP_DIR}"

echo "[$(date -Iseconds)] Starting TimescaleDB backup → ${BACKUP_FILE}"

# Dump only the audit_log table (compressed)
pg_dump \
  --dbname="${DB_URL}" \
  --table=audit_log \
  --no-owner \
  --no-acl \
  --format=plain \
  | gzip > "${BACKUP_FILE}"

echo "[$(date -Iseconds)] Backup complete: $(du -sh "${BACKUP_FILE}" | cut -f1)"

# Verify the backup is readable
gunzip -t "${BACKUP_FILE}" && echo "[$(date -Iseconds)] Backup integrity OK"

# Upload to S3 (optional — set S3_BUCKET to enable)
if [[ -n "${S3_BUCKET:-}" ]]; then
  aws s3 cp "${BACKUP_FILE}" "s3://${S3_BUCKET}/dlp-audit-backups/" \
    --sse aws:kms \
    --storage-class STANDARD_IA
  echo "[$(date -Iseconds)] Uploaded to s3://${S3_BUCKET}/dlp-audit-backups/"
fi

# Purge backups older than RETENTION_DAYS
find "${BACKUP_DIR}" -name "audit_log_*.sql.gz" -mtime "+${RETENTION_DAYS}" -delete
echo "[$(date -Iseconds)] Purged backups older than ${RETENTION_DAYS} days"
