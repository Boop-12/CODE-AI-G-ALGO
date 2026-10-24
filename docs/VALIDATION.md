# Validation evidence - 24 October 2026

## Passed locally

- Backend: 14 integration tests passed; 2 PostgreSQL-specific concurrency tests skipped on SQLite. A Starlette warning recommends httpx2 for future TestClient compatibility; the current httpx adapter completed the tests successfully.
- Covered: login/logout/revocation/expiry, password/session hashing, admin access, per-user ownership, order idempotency, explicit fills, positions/cash accounting, pending buy/sell reservations, quantity/exposure limits, UTC daily realized loss cap, strategy transitions/allocation, broker disconnection, kill switch, Origin checks, profile consent, support persistence and payment unavailability.
- Frontend: npm run lint, npm run typecheck and npm run build succeeded. Production build uses Next.js's supported Webpack builder. Turbopack crashed on this Windows host, including outside the sandbox; no Turbopack success is claimed.
- Migration: isolated SQLite database upgraded from empty, alembic check reported no schema drift, downgraded to base and upgraded again. Generic SQLAlchemy UUID types corrected SQLite portability. PostgreSQL migration verification remains for CI.
- Both local and production Docker Compose configurations passed docker compose config --quiet. Workflow and Compose YAML parsed successfully. Ubuntu deployment scripts passed bash -n syntax checks.
- Browser: mobile and desktop layouts visually inspected. Synthetic local registration completed. Paper BUY submission displayed pending; explicit Simulate fill displayed filled; positions showed one RELIANCE at INR 2,952.40; cash decreased to INR 997,047.60 and equity remained INR 1,000,000 at the fixed quote. Screenshot: screenshots/paper-workspace.png. Synthetic records are in an ignored local database only.
- Git exclusions checked for .env, private keys, virtual environments, node_modules, .next and runtime databases.

## Passed in GitHub CI

Run: https://github.com/Boop-12/CODE-AI-G-ALGO/actions/runs/40108071310 . Tested executable source commit: f7ba8cf2732b992a192ab7e2e0c81240012e4472.

- Backend job succeeded against PostgreSQL 17: **16 tests passed**, including concurrent reservation and double-fill tests. Migration upgrade, schema-drift comparison, downgrade and re-upgrade all passed on PostgreSQL.
- Frontend job succeeded: clean npm ci, lint, production build and typecheck.
- Container job succeeded: backend/frontend Docker images built, Docker Compose reached healthy startup, and Nginx-to-API readiness request passed.
- Docker Desktop was unavailable locally; container runtime verification was performed on the GitHub Ubuntu runner.

## Not verified

- The manual Oracle deployment workflow has not run. CI on a GitHub runner is not a live Oracle deployment.
- Oracle SSH: server reachable on port 22, but available local key rejected with Permission denied (publickey). No server modifications made.
- Public DNS, Cloudflare account/zone, origin certificate, OCI firewall, server sizing, public HTTPS and database restore drill remain unverified.
- Full automated browser end-to-end coverage, accessibility audit, real market/broker integrations, payments, identity verification and live trading are not completed.

The attached brief's full commercial scope is not marked complete. See IMPLEMENTATION_CHECKLIST.md for delivered, mocked and pending features.
