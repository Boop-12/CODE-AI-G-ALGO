#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose -f docker-compose.yml -f docker-compose.production.yml config --quiet
docker compose -f docker-compose.yml -f docker-compose.production.yml ps
docker compose -f docker-compose.yml -f docker-compose.production.yml exec -T nginx nginx -t
curl --fail --show-error https://gnkalgo.com/api/ready
curl --fail --show-error https://gnkalgo.com/api/health
