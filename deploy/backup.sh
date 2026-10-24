#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
umask 077
mkdir -p backups
backup="backups/gnkalgo-$(date -u +%Y%m%dT%H%M%SZ).dump"
docker compose exec -T postgres sh -ec 'PGPASSWORD="$POSTGRES_PASSWORD" exec pg_dump -h 127.0.0.1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$backup"
if [[ ! -s "$backup" ]]; then echo "Backup is empty" >&2; exit 1; fi
sha256sum "$backup" > "$backup.sha256"
echo "Created $backup. Copy it to encrypted off-server storage and verify a restore."
