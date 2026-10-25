#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
compose=(docker compose -f docker-compose.yml -f docker-compose.production.yml)
action=${1:-status}
case "$action" in
    status) "${compose[@]}" ps -a ;;
    start)
        python3 deploy/preflight.py
        "${compose[@]}" up -d --wait --wait-timeout 180
        ;;
    stop) "${compose[@]}" stop nginx web api postgres ;;
    restart)
        python3 deploy/preflight.py
        "${compose[@]}" restart postgres api web nginx
        "${compose[@]}" up -d --wait --wait-timeout 180
        ;;
    build) "${compose[@]}" build --pull ;;
    deploy) bash deploy/deploy.sh ;;
    update)
        git diff --quiet && git diff --cached --quiet || { echo 'Commit or preserve tracked server edits before updating.' >&2; exit 1; }
        bash deploy/backup.sh
        git pull --ff-only origin main
        bash deploy/deploy.sh
        ;;
    logs)
        service=${2:-nginx}
        case "$service" in api|web|nginx|postgres|migrate) ;; *) echo 'Unknown service' >&2; exit 1 ;; esac
        "${compose[@]}" logs --tail=100 -f "$service"
        ;;
    nginx-test) "${compose[@]}" run --rm --no-deps nginx nginx -t ;;
    nginx-recreate)
        python3 deploy/preflight.py
        "${compose[@]}" run --rm --no-deps nginx nginx -t
        "${compose[@]}" up -d --no-deps --force-recreate nginx
        ;;
    health) bash deploy/validate.sh ;;
    *) echo 'Usage: bash deploy/service.sh {status|start|stop|restart|build|deploy|update|logs [service]|nginx-test|nginx-recreate|health}' >&2; exit 1 ;;
esac
