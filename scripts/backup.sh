#!/bin/bash
# Backup script for MariaDB – runs as a one-shot container
# Usage: docker compose --profile backup run --rm backup
set -euo pipefail

BACKUP_DIR="/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
FILENAME="minigolf_${TIMESTAMP}.sql.gz"
RETAIN_DAYS="${BACKUP_RETAIN_DAYS:-30}"

echo "[$(date)] Starting backup..."

mariadb-dump \
  --host="${DATABASE_HOST}" \
  --user="${MYSQL_USER}" \
  --password="${MYSQL_PASSWORD}" \
  --single-transaction \
  --routines \
  --triggers \
  "${MYSQL_DATABASE}" \
  | gzip > "${BACKUP_DIR}/${FILENAME}"

echo "[$(date)] Backup created: ${FILENAME}"

# Rotate: delete backups older than RETAIN_DAYS
find "${BACKUP_DIR}" -name "minigolf_*.sql.gz" -mtime +${RETAIN_DAYS} -delete
echo "[$(date)] Cleaned up backups older than ${RETAIN_DAYS} days."

# Optional: push to remote (e.g., Raspberry Pi)
if [ -n "${BACKUP_REMOTE_HOST:-}" ] && [ -n "${BACKUP_REMOTE_USER:-}" ] && [ -n "${BACKUP_REMOTE_PATH:-}" ]; then
  echo "[$(date)] Pushing backup to ${BACKUP_REMOTE_HOST}..."
  # NOTE: For this to work, you need SSH keys mounted or an SSH agent.
  # Mount your .ssh directory as a volume in docker-compose.yml:
  #   volumes:
  #     - ~/.ssh:/root/.ssh:ro
  if command -v rsync &> /dev/null; then
    rsync -az "${BACKUP_DIR}/${FILENAME}" \
      "${BACKUP_REMOTE_USER}@${BACKUP_REMOTE_HOST}:${BACKUP_REMOTE_PATH}/"
    echo "[$(date)] Push complete."
  else
    echo "[$(date)] rsync not available, skipping push."
  fi
fi

echo "[$(date)] Backup finished successfully."
