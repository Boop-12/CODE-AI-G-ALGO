# GNK Algo

A branded trading research and **manual paper-trading MVP** for gnkalgo.com. Built on the supplied Next.js 16 / React 19 / TypeScript / Tailwind and FastAPI / SQLAlchemy foundation, with PostgreSQL and Docker. The supplied logo is preserved at frontend/public/brand/gnkalgo.png.

## Start locally

Start Docker Desktop's Linux engine, then from D:\CODE-AI-G-ALGO:

```powershell
if (!(Test-Path .env)) { Copy-Item .env.example .env }
# Edit POSTGRES_PASSWORD in .env. Keep the file private.
docker compose up --build -d --wait
```

Open http://localhost . Register with your own email and a 12+ character password. Account creation grants INR 1,000,000 of virtual capital, not real funds. Create an order, then use Orders -> Simulate fill to update positions. Pending orders reserve virtual cash or holdings. The application cannot execute live orders.

For native Windows development, migration commands, GitHub setup, Oracle Ubuntu deployment, Cloudflare DNS/TLS, backups and rollback, follow **[the step-by-step deployment guide](docs/ORACLE_UBUNTU_DEPLOYMENT.md)**.

## Included

- Supplied GNK branding; responsive light/dark workspace, market watch and searchable demonstration quotes.
- Registration/login/logout; PBKDF2 password hashes, opaque hashed database sessions, HttpOnly cookies, expiry and Origin checks.
- Per-user paper accounts/orders/positions/audit trails; admin authorization and interactive bootstrap.
- Strategy configuration states/allocation caps; mock broker connection controls.
- Replay-safe order submission/fills, pending-order reservations, exposure/quantity/realized daily loss checks, and pause-all switch.
- Profile/consent onboarding, original educational articles, a free paper plan and stored support requests.
- Explicit Alembic migration, integration tests, health checks, Docker, Nginx origin TLS, GitHub CI and manual Oracle deployment workflow.

## Release boundaries

This is not a finished commercial/live trading product. Prices are fixed demonstration data. Strategy activation saves configuration; it does not start automated orders. KYC identity verification, email verification/recovery/MFA, real brokers/feeds, payments, publishing, advanced administration, historical analytics and production monitoring remain pending. See [implementation status](docs/IMPLEMENTATION_CHECKLIST.md) and [validation evidence](docs/VALIDATION.md).

## Checks

```powershell
Set-Location backend
.\venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\venv\Scripts\python.exe -m pytest tests -q
Set-Location ..\frontend
npm ci
npm run lint
npm run build
npm run typecheck
```

Tests use an isolated SQLite test database by default. GNK_TEST_DATABASE_URL opts into a dedicated disposable PostgreSQL test database; tests recreate its schema. CI provides that database. Do not point tests at production. Next builds/dev use Webpack because the local Windows Turbopack worker crashed during verification.

## Documents

- docs/REA_ANALYSIS.md: observed reference evidence and unknowns.
- docs/FEATURE_MATRIX.md: reference and implementation status.
- docs/SYSTEM_ARCHITECTURE.md: retained stack, data flow and security model.
- docs/DATABASE_DESIGN.md and docs/API_SPECIFICATION.md.
- docs/IMPLEMENTATION_CHECKLIST.md and docs/DEVELOPMENT_ROADMAP.md.
- docs/ORACLE_UBUNTU_DEPLOYMENT.md and docs/VALIDATION.md.

No default password, broker credential or payment credential is bundled. Never commit .env, private keys, runtime databases or backups. The application ports/database remain internal in the deployment stack. Oracle deployment and public domain verification require functioning server access and domain ownership.
