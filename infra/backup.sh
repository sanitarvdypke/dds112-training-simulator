#!/usr/bin/env sh
set -eu
mkdir -p ./backups
TS=$(date +%Y%m%d_%H%M%S)
pg_dump "${DATABASE_URL:-postgresql://dds112:dds112@localhost:5432/dds112}" > "./backups/dds112_${TS}.sql"
