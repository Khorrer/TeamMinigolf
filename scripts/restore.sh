#!/bin/bash
# Restore a MariaDB backup
# Usage: ./scripts/restore.sh <backup_file.sql.gz>
set -euo pipefail

if [ $# -eq 0 ]; then
  echo "Usage: $0 <backup_file.sql.gz>"
  echo ""
  echo "Available backups:"
  docker compose run --rm backup ls -lh /backups/
  exit 1
fi

BACKUP_FILE="$1"
echo "⚠  This will OVERWRITE the current database!"
read -p "Are you sure? (yes/no): " confirm
if [ "$confirm" != "yes" ]; then
  echo "Aborted."
  exit 0
fi

echo "Restoring from ${BACKUP_FILE}..."

# If it's a .gz file
if [[ "$BACKUP_FILE" == *.gz ]]; then
  docker compose exec -T db bash -c \
    "gunzip < /dev/stdin | mariadb -u\${MYSQL_USER} -p\${MYSQL_PASSWORD} \${MYSQL_DATABASE}" \
    < "$BACKUP_FILE"
else
  docker compose exec -T db bash -c \
    "mariadb -u\${MYSQL_USER} -p\${MYSQL_PASSWORD} \${MYSQL_DATABASE}" \
    < "$BACKUP_FILE"
fi

echo "Restore complete."
