# Validation evidence - 25 October 2026

## Passed locally

- Backend: 17 integration tests passed; 2 PostgreSQL-specific concurrency tests skipped on SQLite. Coverage includes email verification, hashed password-reset tokens/session revocation, profile preferences, session listing, MFA enforcement at the admin boundary, and admin pagination/roles in addition to the existing paper trading flows.
- Covered: login/logout/revocation/expiry, password/session hashing, admin access, per-user ownership, order idempotency, explicit fills, positions/cash accounting, pending buy/sell reservations, quantity/exposure limits, UTC daily realized loss cap, strategy transitions/allocation, broker disconnection, kill switch, Origin checks, profile consent, support persistence and payment unavailability.
- Frontend: npm run lint, npm run typecheck and npm run build succeeded on Next.js 16.4.3. Production dependency audit reports no advisories; the patched development dependency tree also reports zero vulnerabilities. Production build uses Next.js's supported Webpack builder. Turbopack crashed on this Windows host, including outside the sandbox; no Turbopack success is claimed.
- Migration: the account-security migration upgraded, downgraded and upgraded again on an isolated SQLite database. PostgreSQL migration verification remains for CI.
- Both local and production Docker Compose configurations passed docker compose config --quiet. Workflow and Compose YAML parsed successfully. Ubuntu deployment scripts passed bash -n syntax checks.
- Browser: the dedicated registration page was exercised against local SQLite-backed services; registration returned its development verification link with no console errors. The registration page rendered at 390px with no horizontal overflow. The full account/admin flow was not browser-automated. Existing synthetic paper trading evidence remains in the prior screenshot and ignored local database.
- Git exclusions checked for .env, private keys, virtual environments, node_modules, .next and runtime databases.

## Passed in GitHub CI

Run: https://github.com/Boop-12/CODE-AI-G-ALGO/actions/runs/40108071310 . Tested executable source commit: f7ba8cf2732b992a192ab7e2e0c81240012e4472.

- Backend job succeeded against PostgreSQL 17: **16 tests passed**, including concurrent reservation and double-fill tests. Migration upgrade, schema-drift comparison, downgrade and re-upgrade all passed on PostgreSQL.
- Frontend job succeeded: clean npm ci, lint, production build and typecheck.
- Container job succeeded: backend/frontend Docker images built, Docker Compose reached healthy startup, and Nginx-to-API readiness request passed.
- Docker Desktop was unavailable locally; container runtime verification was performed on the GitHub Ubuntu runner.

## Not verified

- The manual Oracle deployment workflow has not run. CI on a GitHub runner is not a live Oracle deployment.
- Cloudflare account settings and OCI firewall rules were not independently audited. Public DNS/HTTPS and origin connectivity were verified as described below. Off-server backup storage and a database restore drill remain pending.
- Full automated browser end-to-end coverage, accessibility audit, real market/broker integrations, payments, identity verification and live trading are not completed.

The attached brief's full commercial scope is not marked complete. See IMPLEMENTATION_CHECKLIST.md for delivered, mocked and pending features.

## Live Oracle recovery and deployment - 25 October 2026

- Used the user-provided PuTTY key with a pinned server host fingerprint. Preserved newer merged authentication code and the existing database/environment.
- Confirmed the actual 521 cause: Docker Nginx could not load /etc/nginx/tls/origin.pem from its /opt/gnkalgo/tls bind mount. API/frontend/PostgreSQL were healthy and migrate exited successfully. The separate Ubuntu Nginx service also had obsolete certificate paths.
- Verified and installed the existing Let's Encrypt certificate/key, recreated only Nginx for initial recovery, and then built all application images, applied migration checks, recreated API/frontend, and refreshed Docker Nginx.
- Expanded the existing certificate to gnkalgo.com, www.gnkalgo.com and app.gnkalgo.com. Certificate expiry: 23 January 2027. The app hostname redirects to the canonical gnkalgo.com site.
- Verified public root/www/login/API readiness returned 200 and app returned 301 to the canonical site. All four running services were healthy. migrate Exited (0) is expected.
- Added production TLS preflight, seven passing certificate/environment tests, Nginx healthcheck, ACME challenge routing, and service commands. GitHub CI succeeded for commits 50ad1a8, bff1d33 and bacb777.
- Installed the root-run Certbot deployment hook to synchronize the renewed certificate/key and validate/reload Docker Nginx. Preserved the obsolete hook outside the active hooks directory. Disabled the failed host nginx.service to avoid competing port ownership.
- Certbot's immediate staging renewal simulation succeeded for all three names. Production certificate issuance also successfully invoked the deployment hook.
- Created a server-local custom-format PostgreSQL backup before deployment. No database volume was removed. No real orders were placed, no production test accounts were created, and no application/private key/database secrets were printed.

Operation commands and incident diagnosis: SERVICE_COMMANDS.md. This verifies the deployed paper platform, not the unimplemented live broker/payment/KYC integrations.
