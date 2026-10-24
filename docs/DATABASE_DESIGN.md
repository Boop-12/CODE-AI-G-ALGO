# Database design

Implemented tables: user, role, user_role (retained foundation), browser_session, paper_account, strategy_deployment, paper_order, paper_position, audit_log, support_ticket. The retained refresh_token and password_reset_token tables are unused legacy scaffolds; their workflows are not implemented and no token records are written there.

Identifiers are UUIDs except hashed session primary keys and one-to-one account user IDs. Money is NUMERIC(18,2), quantities are integers, and new event timestamps are UTC with timezone information. Foreign keys bind records to users. Unique (user_id,idempotency_key), (user_id,symbol), and (user_id,strategy_id) enforce record identity. User email and role names have unique indexes. Passwords and active session tokens are hashed.

The checked-in initial Alembic revision creates this schema. Registration seeds a virtual INR 1,000,000 account. Strategy/quote fixtures live in brokers.py and are explicitly demonstration content. No default login or automatic production administrator is seeded. Run python -m app.bootstrap interactively for an admin.

Future migrations should add permissions, verified profile/KYC records, encrypted authorization references, strategy versions, order events/executions, historical portfolio snapshots, notifications, plans/subscriptions/payments and protected research publishing. These are design targets, not implemented tables.

Do not stamp an existing database blindly: the initial migration assumes empty tables. For a pre-existing schema, back up and compare its schema before designing a baseline migration. SQL logging is disabled. Audit events are application records, not a tamper-proof regulatory ledger.
