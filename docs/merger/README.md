# Merger inspection and preservation record

Inspected locally on 2026-10-25. Target: `D:\CODE-AI-G-ALGO`.
Source: `C:\Gnk_AI_ALGO_Broker`. No production access or real trades are authorized.

## Checkpoint and existing work

- Source HEAD: `9b17adc0c55e1e22b9244b194a11ad05e771d85b`, branch `cursor/broker-status-playwright-setup`.
- Target HEAD before merger: `dc23b5a49ca1676213593f7d2dd8ec6e165ed7cc`, branch `main`; remote main matched this SHA at inspection.
- Source already has a deleted `GNK_AI` Git entry, modified Playwright files and changed/deleted test artifacts. Preserve all of these; do not restore or commit them as merger work.
- Target was clean, with ignored `.env`, local databases, virtual environment and frontend build/dependency directories. These are not merger inputs or commit candidates.
- Private working-file ZIPs (67 source files, 110 target files), full Git bundles and SHA-256 manifests were saved under this chat's `work/merger-checkpoint` before edits. The ZIPs contain private local configuration/data and must remain outside Git. Generated dependencies/build caches are excluded and can be reinstalled.
- Recovery: inspect ZIPs without overwriting either checkout; restore into a new directory and use the matching Git bundle. The manifest records absent files through the original Git status. Never restore over newer user work, reset a database, or deploy as part of this merger.

## Architecture and feature-preservation matrix

| Feature | Source project | Target project | Merge action |
| --- | --- | --- | --- |
| Frontend | Next.js ^16.3.8, React 19.2.0, TypeScript, Tailwind 4, npm lockfile | Next.js 16.4.3, React 19.2.8, TypeScript, Tailwind 4, npm lockfile | Retain target framework/lockfile; integrate source public page without framework changes |
| Public website | Homepage, Approach/Platform anchors, registration/sign-in links, supplied JPG, 3 themes and 4 accents | `/` renders guest-capable paper workspace; supplied PNG branding | Preserve source public content and JPG bytes at `/`; preserve existing target PNG and every existing asset; isolate public styles from portal |
| Authentication | FastAPI sync SQLAlchemy, Argon2, JWT access in memory, rotating HttpOnly refresh cookie; registration/reset/logout | FastAPI 0.142.2 async SQLAlchemy, PBKDF2 600000, opaque hashed HttpOnly sessions, verification/recovery/MFA | Retain target session system; do not combine competing auth handlers or accept source JWTs as target credentials |
| Routes | `/`, `/login`, `/register`, `/forgot-password`, `/reset-password`, `/account` | All requested auth/user/admin routes; `/admin/mfa` | Preserve target routes; add `/account` compatibility redirect; preserve guest workspace at `/workspace` |
| APIs | `/api/v1/auth/*`, `/users/me`, permission-gated `/admin/users`, `/healthz` | `/auth/*`, `/me`, profile/settings/admin, trading, support, health/readiness | Keep target API shapes and admin gates; compatibility requires explicit mapping, not redirecting incompatible JSON responses |
| Database | PostgreSQL (SQLite dev/test), integer `users` IDs, authorities/role joins, refresh/reset tokens; migration `0001_auth_schema` | PostgreSQL (SQLite tests), UUID `user` IDs, sessions/MFA, paper accounts/orders/positions, logs/support; 2 Alembic revisions | Preserve both histories and data. Never apply source migrations to target. Account import needs ID/hash/permission mapping and conflict policy; leave pending |
| User portal | Basic account page | Protected dashboard/profile/preferences/security/sessions/login history | Retain richer target portal and secure source route compatibility |
| Admin | Authority-based backend listing; no standalone admin UI | Role/MFA-gated portal, paginated search, details, super-admin status/roles/settings, audit | Preserve target backend enforcement. Audit MFA session behavior before claiming production security |
| Trading/risk | No trading engine found in supplied checkout | Manual paper submit/fill/cancel, tenant isolation, idempotency, reservations, exposure/loss/quantity limits, pause-all | Preserve target implementation and regression tests; no live mode, orders or new broker connections |
| Broker/market | No broker adapters or live feeds found; deleted `GNK_AI` entry is not available source | MockBroker and fixed demonstration quotes | Preserve mock broker. Do not infer missing nested checkout functionality from older notes |
| Strategies/backtesting | Not found | 3 stored strategy configurations; no signals/backtesting | Preserve configuration; document limitations, do not claim automated execution |
| Other features | Theme controls, password strength policy, sanitized validation errors | Onboarding consent, educational articles, free paper subscription, stored support tickets | Preserve target modules; port useful security behavior with tests |
| Jobs/notifications | Background password-reset email; Redis rate limits | SMTP email via thread; Nginx auth/API throttling; certificate renewal scripts | Preserve SMTP and proxy throttling; no scheduler/trading workers found |
| Deployment | Compose PostgreSQL/Redis/API/web/Nginx; HTTPS/ACME overrides | Compose PostgreSQL/API/web/Nginx, TLS preflight/backup/service/renewal scripts | Retain target deployment files; never run production scripts. Existing www HTTPS server proxies `/login` and `/api` on the same origin |
| Tests | Pytest auth suite, Playwright login seed (locally modified) | Pytest platform suite, deployment preflight unittest, CI PostgreSQL concurrency/migrations, frontend lint/build/types | Run isolated target regressions; add public-route/style/branding browser checks and security regressions |
| Configuration | JWT issuer/audience/secrets, Redis/SMTP, frontend origin, DB | SECRET_KEY, sessions/cookies/origins, SMTP, app URL, PostgreSQL | Keep examples and private files; no secrets copied, printed or committed |

The JSON inventories list non-private working files and their pre-change hashes. They cover application modules, migrations, tests, scripts, docs and deployment files; generated dependencies and build outputs are not source merger inputs. Environment values and database contents were not printed or inspected.

## Incremental implementation and acceptance

1. Checkpoint, inventory and immutable-asset verification; commit/push only these safe additions after checking them.
2. Integrate original public homepage/theme controls, exact source image bytes, `/login` navigation and route compatibility; verify browser behavior, style isolation and original assets; lint/build/types and backend regressions; commit/push.
3. Port applicable auth security protections with dedicated regressions, preserving all paper/admin tests; commit/push.
4. Account/data migration is deliberately pending: integer/UUID identities, existing email collisions, Argon2/PBKDF2 and authority/admin-role differences must be resolved without granting new permissions. No schema reset or production migration is authorized. A copy of the actual source database and an approved collision/role policy are required for a tested data import. Existing source sessions should not become target sessions.

No cleanup deletions are proposed. Source modules, migrations, themes, deployment files, lockfiles and local work remain protected. The target already has the requested account/admin functionality; duplicating the source auth service would create ambiguous identity and authorization behavior.

## Local workflow and external verification

Use target README for Docker or native development. Local login is `http://localhost/login` through the development proxy, or `http://localhost:3000/login` with the frontend and API running. Native backend: `backend/venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000` from backend, using private local configuration; frontend: `npm run dev` from frontend. Do not run migrations against any existing database without a separate backup and review.

The production Nginx configuration already accepts `www.gnkalgo.com` and forwards frontend paths and `/api` separately. Actual DNS/TLS/SMTP/delivery, live website equivalence and a clean production restart require a later authorized deployment; none is executed here. Deployment workflow is manual `workflow_dispatch`, so milestone pushes do not invoke it. Keep commits on a merger branch until the entire accepted scope is ready.

## Milestone 1 validation

- Target baseline: 17 platform tests passed; 2 PostgreSQL-only concurrency tests skipped on isolated SQLite.
- Deployment preflight: 3 environment checks passed; 4 certificate checks skipped because OpenSSL was not on PATH.
- Protected assets: all 7 original frontend assets match their SHA-256 hashes; Git whitespace check passed.
- CI now runs on `merger/**` pushes and checks protected asset hashes. Production deployment remains manual-only.
- User clarification: the final database technology is PostgreSQL and strong password security is required. Schema differences above remain observed code facts; final records must be unified through a tested additive import, never a reset. Prefer Argon2 for new hashes, retaining verification and gradual upgrade of existing PBKDF2 hashes.

## Milestone 2: public-site integration

- `/` now renders the original source homepage content, navigation, theme/accent controls and original JPG. Existing target PNG/SVG/favicon bytes were not changed. Source JPG was added under its original URL, with a matching SHA-256 checksum.
- Source CSS is scoped through a CSS Module. Appearance data attributes live on the public-site wrapper, preventing source themes from altering account/admin/trading pages. Sign In remains visible on mobile.
- `/dashboard` remains the authenticated trading portal. `/workspace` preserves the former guest workspace. Legacy `/account` redirects to protected `/profile`. Existing target auth/admin routes remain intact.
- Locked dependencies installed successfully; Next.js 16.4.3 production build, lint and type checking pass. Three Chromium browser regressions pass: public content/assets/theme persistence and same-domain sign-in; mobile/protected/compatibility routes; account registration, dashboard, simulated order/fill, persistence after refresh, ordinary-user admin rejection and logout.
- Browser backend always creates a fresh temporary SQLite database and disables SMTP; it cannot use private local configuration or send real orders. CI runs the same tests against the production frontend build. Traces and screenshots are disabled to avoid recording passwords/tokens.
- No databases, environment files, existing branding assets, broker modules or trading modules were modified. No source files were deleted. Production website matching remains unverified because production was not accessed or deployed.

Reproduce browser checks from frontend: set `API_INTERNAL_URL=http://127.0.0.1:18080` before `npm run build`; set `GNK_TEST_PYTHON` to the backend virtual-environment Python (or install backend dev requirements into the active Python), then run `npm run test:e2e`. The tests start and stop only their own local servers on ports 13000/18080 and refuse to reuse existing servers.
