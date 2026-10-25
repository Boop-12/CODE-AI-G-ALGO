# GNK Algo service operations on Oracle Ubuntu

Run these commands on the server, not in Windows PowerShell.

```bash
cd /opt/CODE-AI-G-ALGO
```

The application uses Docker Nginx. Do not start the separate Ubuntu nginx.service on the same ports. API/web/database are internal containers; only Nginx publishes 80/443. Migration is a one-off job: Exited (0) is its expected successful state.

## Quick commands

```bash
# Show all services, including the one-off migration job
bash deploy/service.sh status

# Start services with the production configuration
bash deploy/service.sh start

# Stop services; keep containers and persistent database volume
bash deploy/service.sh stop

# Restart PostgreSQL, API, frontend and Nginx, then wait for health
bash deploy/service.sh restart

# Build images without restarting services
bash deploy/service.sh build

# Build, apply migrations and deploy this checked-out revision
bash deploy/service.sh deploy

# Back up DB, pull main without overwriting edits, build/migrate/deploy
bash deploy/service.sh update

# Follow logs; Ctrl+C exits log viewing and does not stop the service
bash deploy/service.sh logs nginx
bash deploy/service.sh logs api
bash deploy/service.sh logs web
bash deploy/service.sh logs postgres
bash deploy/service.sh logs migrate

# Validate proxy configuration and recreate only Nginx after a TLS/mount change
bash deploy/service.sh nginx-test
bash deploy/service.sh nginx-recreate

# Public readiness/health checks
bash deploy/service.sh health
```

Use deploy/update to install changed source code. A restart alone does not rebuild images or apply new code. Never use docker compose down -v unless deliberately deleting the database.

## Equivalent direct Docker commands

```bash
DC='docker compose -f docker-compose.yml -f docker-compose.production.yml'
$DC ps -a
$DC up -d --wait --wait-timeout 180
$DC stop nginx web api postgres
$DC restart postgres api web nginx
$DC build --pull
$DC logs --tail=100 -f nginx
$DC run --rm migrate
$DC run --rm --no-deps nginx nginx -t
$DC up -d --no-deps --force-recreate nginx
```

For a complete update prefer service.sh update so backups, TLS checks, builds and migrations run in order. Preserve untracked server files; do not run git clean or overwrite .env. The update command stops if tracked files have local edits.

## Certificate setup

Nginx expects origin.pem and origin.key inside TLS_DIR. A CSR is a certificate request, not a signed certificate. This host already has a publicly trusted Let's Encrypt certificate at /etc/letsencrypt/live/gnkalgo.com now covering gnkalgo.com, www.gnkalgo.com and app.gnkalgo.com. The app hostname redirects to the canonical gnkalgo.com site. A publicly trusted origin certificate also works with Cloudflare Full (strict); a separate Cloudflare Origin CA certificate is not required.

The Docker TLS copy lives under /opt/gnkalgo/tls. The private key stays server-side with mode 600; TLS_DIR is private to the deploy account. For a Cloudflare-issued origin certificate, also provide its CA root bundle and set TLS_CA_FILE or ORIGIN_CA_FILE. Otherwise the preflight uses the Ubuntu system CA bundle.

preflight.py verifies production environment, certificate lifetime, hostnames, trust chain and certificate/key match before a build or migration. It never prints environment secrets. Existing database passwords are preserved; changing .env alone does not rotate an initialized PostgreSQL role password.

The existing Certbot webroot is /opt/gnkalgo_AI/certbot/www. Production Nginx mounts it read-only and serves /.well-known/acme-challenge/ over HTTP and HTTPS. After successful renewal, deploy/renew-letsencrypt.sh copies the renewed chain/key to the Docker mount and validates/reloads Docker Nginx. The installed hook is /etc/letsencrypt/renewal-hooks/deploy/gnkalgo-docker.sh.

```bash
systemctl status certbot.timer --no-pager
sudo certbot renew --dry-run
```

Do not run systemctl start nginx for this Docker deployment. The obsolete host service/configuration can otherwise conflict with Docker on ports 80/443. The current certificate includes the app hostname; the preflight and renewal hook check coverage for all three hostnames.

## Diagnosing Cloudflare 521

Observed 25 October 2026: api/web/PostgreSQL healthy, migrate Exited (0), nginx Restarting (1), no origin HTTP/HTTPS listener. Nginx logged cannot load certificate /etc/nginx/tls/origin.pem. Certificate files were missing from the actual bind mount, while an unused project tls folder only contained a key/CSR/CA file.

Recovery: verify existing Let's Encrypt chain; install its fullchain and matching key at the configured TLS_DIR; validate Nginx using a one-off container; force-recreate only Nginx to refresh the bind mount. Public root, www, login and API readiness then returned 200. The separate app hostname initially returned 526; the existing Let's Encrypt certificate was expanded to include it. A read-only config warning from the container entrypoint is benign; the certificate [emerg] message is the startup failure.

```bash
$DC ps -a
$DC logs --no-color --tail=80 nginx
sudo ss -ltnp | grep -E ':80 |:443 '
python3 deploy/preflight.py
curl --fail https://gnkalgo.com/api/ready
```

A 521 after local origin HTTPS works requires checking OCI ingress/firewalls and Cloudflare origin DNS. A 526 indicates origin certificate validation failure; do not disable TLS validation to hide it.
