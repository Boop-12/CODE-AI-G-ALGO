#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ ! -f .env ]]; then echo "Create .env from .env.production.example first" >&2; exit 1; fi
ca_file=$(python3 deploy/preflight.py --print-ca)
# This script deploys the checked-out revision; it never resets or pulls your work.
compose=(docker compose -f docker-compose.yml -f docker-compose.production.yml)
"${compose[@]}" config --quiet
"${compose[@]}" build --pull
"${compose[@]}" up -d postgres
# A fresh one-off migration runs on EVERY deployment, even if 'migrate' previously exited.
"${compose[@]}" run --rm migrate
"${compose[@]}" up -d --no-deps --force-recreate --wait --wait-timeout 180 api web
# Test the new bind-mounted configuration before replacing the running proxy.
"${compose[@]}" run --rm --no-deps nginx nginx -t
# Recreate so new config file inodes and changed upstream container IPs are loaded.
"${compose[@]}" up -d --no-deps --force-recreate --wait --wait-timeout 90 nginx
curl --retry 5 --retry-connrefused --retry-delay 2 --fail --show-error --silent --resolve gnkalgo.com:443:127.0.0.1 https://gnkalgo.com/api/ready --cacert "$ca_file"
echo "Local origin ready. Verify the public URL and a paper round trip next."
