# Database design

Implemented tables: user, role, user_role, browser_session, login_history, email_verification_token, password_reset_token, system_setting, paper_account, strategy_deployment, paper_order, paper_position, audit_log and support_ticket. `refresh_token` remains an unused legacy scaffold.

Identifiers are UUIDs except hashed session primary keys and one-to-one account user IDs. Money is NUMERIC(18,2), quantities are integers, and timestamps are UTC. Foreign keys bind records to users. Unique (user_id,idempotency_key), (user_id,symbol), and (user_id,strategy_id) enforce record identity. User email, role names and token hashes have unique indexes. Passwords, reset tokens, email-verification tokens and active session tokens are hashed. TOTP secrets are encrypted with Fernet using a key derived from the server-side SECRET_KEY; keep that key stable or existing MFA secrets cannot be decrypted.

The checked-in Alembic revisions create and extend this schema. Registration seeds a virtual INR 1,000,000 account. Existing accounts are preserved as verified during the security migration; new registrations start unverified and receive expiring one-use verification tokens. Password reset tokens expire after 30 minutes and reset revokes all sessions. Session records include creation time and limited device metadata; successful sign-ins are recorded in login_history. `system_setting` stores the supported platform settings, currently registration availability and support contact email.

Strategy/quote fixtures live in brokers.py and are explicitly demonstration content. No default login or automatic production administrator is seeded. Run `python -m app.bootstrap` interactively for an administrator; sign in and complete TOTP MFA enrollment before accessing admin APIs.

Future migrations should add granular permission scopes, KYC records, encrypted broker authorization references, strategy versions, order events/executions, historical portfolio snapshots, notifications, plans/subscriptions/payments and protected research publishing. These are design targets, not implemented tables.

Do not stamp an existing database blindly: the initial migration assumes empty tables. For a pre-existing schema, back up and compare its schema before designing a baseline migration. SQL logging is disabled. Audit events are application records, not a tamper-proof regulatory ledger.
