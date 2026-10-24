# API specification

Base /api/v1. JSON requests and responses; monetary values serialize as decimal strings. Public health: GET /api/health. Database/schema readiness: GET /api/ready. Development OpenAPI: /api/docs and /api/openapi.json (blocked at production proxy).

| Method | Route | Purpose |
| --- | --- | --- |
| POST | /auth/register | Name, email, password (12-128 characters); creates paper account and cookie |
| POST | /auth/login | Email/password; returns user and session cookie |
| POST | /auth/logout | Deletes session and cookie |
| GET | /me | Authenticated user with roles |
| GET | /market | Public fixed demonstration quotes; no real-time timestamp |
| GET | /dashboard | Paper equity, cash, P&L, configuration count and recent orders |
| GET/PATCH | /strategies, /strategies/{id} | List and change state/allocation |
| POST | /broker | {enabled: boolean}; mock connection only |
| POST | /orders | {symbol, side: BUY or SELL, quantity: integer}; Idempotency-Key header required |
| GET | /orders | Latest 250 current-user orders |
| POST | /orders/{uuid}/fill | Simulate pending order execution; replay-safe |
| POST | /orders/{uuid}/cancel | Cancel pending order; cannot cancel filled orders |
| GET | /positions | Current-user open paper positions |
| POST | /risk/kill-switch | {enabled: boolean}; cancels pending orders and pauses active configurations |
| POST | /onboarding | {name, consent: true}; profile only, identity_verified=false |
| GET | /research | Original education examples |
| GET | /subscription | Free paper plan only |
| POST | /subscription/checkout | Returns 503; payment integration absent |
| GET | /activity | Latest 100 current-user audit events |
| GET/POST | /support | List/create current-user support tickets |
| GET | /admin/overview | Admin-only user and audit lists (latest 100) |

All routes except register/login/market/health/ready require an unexpired HttpOnly gnk_session cookie. Every cookie-authenticated write must include Origin matching ALLOWED_ORIGINS; browser fetch supplies this automatically. Registration ignores no roles field for privilege assignment: roles can only be provisioned server-side. Production Nginx applies auth/API limits.

Order state: pending -> filled or cancelled. Filled and cancelled are terminal; repeating a fill on a filled order returns its result. No partial fills, live orders or automatic pending-order fills exist. Duplicate submission keys return the original order only when symbol, side and quantity match; otherwise 409. Risk failures are 422 or 409. Unknown current-user records return 404. Forbidden roles return 403. Invalid sessions return 401. Request validation returns 422. Upstream/proxy failures are surfaced in the UI; retry order submissions using their original key.
