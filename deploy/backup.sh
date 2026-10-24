#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
umask 077
mkdir -p backups
backup="backups/gnkalgo-$(date -u +%Y%m%dT%H%M%SZ).dump"
docker compose exec -T postgres pg_dump -U postgres -d postgres -Fc > "$backup"
if [[ ! -s "$backup" ]]; then echo "Backup is empty" >&2; exit 1; fi
sha256sum "$backup" > "$backup.sha256"
echo "Created $backup. Copy it to encrypted off-server storage and verify a restore."
