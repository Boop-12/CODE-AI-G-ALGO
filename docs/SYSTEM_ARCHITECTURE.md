# System architecture

Browser -> Cloudflare DNS/TLS -> Oracle Ubuntu 130.210.34.12:443 -> Nginx -> Next.js :3000 / FastAPI :8000 -> PostgreSQL :5432.

All application and database ports are internal to Docker. Only Nginx publishes HTTP/HTTPS. Nginx preserves the complete /api path. Docker health dependencies gate startup on successful migration and database readiness. No missing worker module is launched.

FastAPI is a modular monolith: api/routes.py owns application use cases; api/deps.py authenticates sessions and checks roles; brokers.py contains the adapter protocol and fixed mock prices; models/ contains durable records. The initial implementation does not require Redis, BullMQ or an idle worker. Add these when a real queue consumer exists.

Next.js is built as a standalone Node application. Native local development proxies /api to 127.0.0.1:8000; Docker's Nginx routes /api directly to FastAPI. Client data comes from the backend after sign-in; guest sample values are labeled. No credentials are stored in browser storage.

Passwords use salted PBKDF2-SHA256 (600,000 iterations). Session cookies are HttpOnly, SameSite=Strict, production Secure, and restricted to /api. Session token digests are stored server-side. Cookie-authenticated writes require an allowlisted Origin. Nginx limits auth/API request rates; API is not exposed directly in production. Production startup validates HTTPS origin and cookie settings. The secret setting is a deployment guard; sessions are opaque, not signed JWTs.

Financial mutations lock the account row with PostgreSQL SELECT FOR UPDATE. This serializes fills, reservations and risk switches per account across processes. Unique idempotency keys are per user. Order acceptance is not a fill. The separate fill endpoint atomically updates positions, cash, realized results and audit events. The adapter is fixed-price, long-only and paper-only. SQLite is a local/testing convenience; it does not validate PostgreSQL row-lock behavior.

Origin TLS uses Cloudflare Origin CA and Full (strict). Origin CA certificates are for Cloudflare-to-origin encryption; browsers do not generally trust direct origin connections. Database persistence uses a named volume; backup scripts create custom-format dumps. A single VM remains a single point of failure.
