# Roadmap

1. Delivered foundation: reuse FastAPI/Next.js, original GNK interface, authentication, paper accounts, configuration states, manual simulated fills, risk controls and deployment files.
2. Validate staging: PostgreSQL integration/concurrency tests, complete browser journeys on mobile and desktop, database recovery drill, dependency/security audit and Oracle capacity measurement.
3. Complete identity: email verification, recovery, MFA, session revocation, KYC provider/private storage, consent versions, review roles, retention and audit access.
4. Complete paper engine: append-only order event/execution ledger, partial/rejected fills, fees/slippage, licensed or clearly simulated changing quotes, queue workers, scheduling, strategy versions, stop losses and historical analytics.
5. Complete product: research authoring/disclosures/access, subscription entitlements, gateway checkout/signed webhooks/invoices, notifications and operational admin/support tools.
6. Before live trading: review current broker/exchange/regulatory requirements with qualified advisers, threat model and independent audit, encrypted broker token vault, reconciliation and fail-safe broker connectivity, operational monitoring, explicit live-mode user consent and controlled rollout. This release contains no live execution path.

Prioritize paper correctness and operational recovery before commercial billing or live brokerage connectivity. See IMPLEMENTATION_CHECKLIST.md for precise module boundaries and VALIDATION.md for observed checks.
