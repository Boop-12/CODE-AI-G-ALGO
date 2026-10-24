# Implementation checklist and release status

Inspected on 24 October 2026. Starting folder was not a Git checkout. Existing Next.js 16 / React 19 / Tailwind and FastAPI / SQLAlchemy / Alembic foundations retained. NestJS/Prisma were preferences in the attachment, not a reason to discard working framework setup.

- [x] Original GNK visual identity using the supplied PNG; responsive light/dark dashboard.
- [x] Registration, password login, opaque hashed database sessions, expiry, logout, Origin checks.
- [x] Server-side authorization and tenant isolation; administrator bootstrap and read-only overview.
- [x] PostgreSQL-compatible UUID/decimal schema and explicit Alembic initial migration.
- [x] Mock quote adapter; paper broker connect/disconnect.
- [x] Strategy configuration with active/paused/stopped states and aggregate allocation limit.
- [x] Manual paper order submit, explicit simulated fill, cancel, idempotency and position accounting.
- [x] Pending cash/holding reservations, quantity/exposure/daily realized loss limits, kill switch and audit events.
- [x] Basic paper account metrics, research education, free subscription status, stored support requests.
- [x] Profile and simulation consent onboarding, with identity verification explicitly absent.
- [x] Docker configuration, health checks, TLS origin configuration, CI and manual deployment workflow.
- [x] Local-to-GitHub-to-Oracle-to-Cloudflare runbook and backup/rollback instructions.
- [ ] Email/mobile verification, password recovery, MFA, session management UI and abuse protection beyond proxy limits.
- [ ] KYC provider, encrypted private document storage, review workflow and retention controls.
- [ ] Live broker adapters, token encryption/refresh, licensed market feed, streaming and reconciliation.
- [ ] Automated strategy signals, stop-loss engine, backtests, strategy versioning and worker scheduling.
- [ ] Partial fills/rejections, dedicated execution ledger and event history, fees/slippage and portfolio snapshots.
- [ ] Paid plan entitlements, payment gateway/webhook verification, invoices and renewals.
- [ ] Research publishing/upload/download permissions and full admin user/role/support management.
- [ ] Production security review, operational alerting, off-server backups and tested disaster recovery.
- [ ] Verified PostgreSQL concurrency tests, full browser end-to-end tests, live Oracle deployment and public DNS/TLS checks.

This is a functional paper-trading MVP, not a finished regulated live-trading product. No live execution route exists. Fixed quotes mean actual market performance cannot be inferred. Strategy activation records configuration and does not start automated trades. Paper sessions intentionally allow practice outside market hours. Daily loss resets at UTC midnight in this MVP.
