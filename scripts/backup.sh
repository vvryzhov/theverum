#!/bin/sh
set -eu
mkdir -p backups
STAMP=$(date +%Y%m%d_%H%M%S)
docker compose exec -T postgres pg_dump -U theverum theverum | gzip > backups/postgres_${STAMP}.sql.gz
echo "Backup: backups/postgres_${STAMP}.sql.gz"
