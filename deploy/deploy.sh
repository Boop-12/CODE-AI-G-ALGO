#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ ! -f .env ]]; then echo "Create .env from .env.production.example first" >&2; exit 1; fi
# This script deploys the checked-out revision; it never resets or pulls your work.
compose=(docker compose -f docker-compose.yml -f docker-compose.production.yml)
"${compose[@]}" config --quiet
"${compose[@]}" build --pull
"${compose[@]}" up -d postgres
# A fresh one-off migration runs on EVERY deployment, even if 'migrate' previously exited.
"${compose[@]}" run --rm migrate
"${compose[@]}" up -d --wait --wait-timeout 180
"${compose[@]}" exec -T nginx nginx -t
curl --fail --show-error --silent --resolve gnkalgo.com:443:127.0.0.1 https://gnkalgo.com/api/ready --cacert "${ORIGIN_CA_FILE:-/opt/gnkalgo/tls/cloudflare-origin-ca.pem}"
echo "Local origin ready. Verify the public URL and a paper round trip next."
