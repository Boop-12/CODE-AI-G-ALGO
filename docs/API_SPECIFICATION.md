# API specification

Base /api/v1. JSON requests and responses; monetary values serialize as decimal strings. Public health: GET /api/health. Database/schema readiness: GET /api/ready. Development OpenAPI: /api/docs and /api/openapi.json (blocked at production proxy).

| Method | Route | Purpose |
| --- | --- | --- |
| POST | /auth/register | Name, email, password (12-128 characters); creates paper account and cookie |
| POST | /auth/login | Email/password; returns user and session cookie |
| POST | /auth/logout | Deletes session and cookie |
| POST | /auth/verify-email | Consume a hashed, single-use email-verification token |
| POST | /auth/resend-verification | Send a new email verification link to the signed-in user |
| POST | /auth/forgot-password | Request a time-limited password reset link; response does not reveal account existence |
| POST | /auth/reset-password | Set a new password and revoke all existing sessions |
| POST | /auth/mfa/setup, /auth/mfa/verify, /auth/mfa/disable | Enroll or disable an authenticator with code verification; secret is encrypted at rest |
| GET | /me | Authenticated user with roles |
| GET/PATCH | /profile | Read or update the signed-in user's profile |
| GET/PATCH | /settings/account | Read or update theme preferences and verification state |
| GET | /settings/security | MFA state, active sessions and successful sign-in history |
| PATCH | /settings/security/password | Change password and revoke all sessions |
| DELETE | /settings/security/sessions/{id} | Revoke another active session owned by the current user |
| GET | /settings/brokers | Read the paper-only broker connection status |
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
| GET | /admin/users | Admin user search and pagination |
| GET | /admin/users/{id} | Admin user detail |
| PATCH | /admin/users/{id}/status | Super-admin account activation/suspension; suspension revokes sessions |
| GET | /admin/roles | Admin role directory |
| PATCH | /admin/users/{id}/roles | Super-admin role assignment |
| GET | /admin/audit-logs | Paginated administrator audit log |
| GET/PATCH | /admin/settings | Persistent registration toggle and support email (super-admin write) |

All routes except register/login/forgot-password/reset-password/verify-email/market/health/ready require an unexpired HttpOnly gnk_session cookie. Every cookie-authenticated write must include Origin matching ALLOWED_ORIGINS; browser fetch supplies this automatically. Registration ignores roles supplied by clients: roles can only be provisioned server-side. Administrator APIs require an admin role and completed TOTP MFA; changing roles, account status, or platform settings additionally requires super_admin. Production Nginx applies a 10-requests/minute auth limit with a small burst, including password reset.

Email verification and recovery URLs are sent through SMTP when configured. With SMTP unset, non-production responses include development-only one-time links; production responses never disclose tokens. Registration remains usable while the email is unverified, and the account settings show its verification status.

Order state: pending -> filled or cancelled. Filled and cancelled are terminal; repeating a fill on a filled order returns its result. No partial fills, live orders or automatic pending-order fills exist. Duplicate submission keys return the original order only when symbol, side and quantity match; otherwise 409. Risk failures are 422 or 409. Unknown current-user records return 404. Forbidden roles return 403. Invalid sessions return 401. Request validation returns 422. Upstream/proxy failures are surfaced in the UI; retry order submissions using their original key.
