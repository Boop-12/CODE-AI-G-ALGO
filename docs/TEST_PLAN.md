# Test Plan

## Objective
Validate the current GNK Algo codebase for correctness, security posture, and release-readiness without triggering live trading.

## Validation executed
- Backend tests: `py -3.14 -m pytest -q`
- Frontend typecheck: `npm run typecheck`
- Frontend lint: `npm run lint`
- Frontend production build: `npm run build`

## Results
- Backend: 25 passed, 2 skipped
- Frontend: typecheck passed, lint passed, build passed
- App-level E2E/browser validation remains blocked because the local project was not served in a browser session during this audit.

## Scope by area

### Authentication
- registration validation
- login/logout behavior
- password hashing and legacy upgrade path
- MFA enrollment and verification
- session expiry and invalidation

### Trading simulation
- pending-order reservation logic
- sell/buy exposure checks
- daily loss limit checks
- kill switch behavior
- broker disconnect handling

### Admin controls
- admin route access control
- user management
- role assignment and suspension rules
- audit log visibility
- settings updates

### Frontend behavior
- route-level page rendering
- auth form validation
- protected public/private navigation
- responsive layout and branding integrity

## Gate criteria
A release candidate is considered acceptable only when:
- critical backend tests pass
- frontend compile and lint checks pass
- no live-trading or broker credential usage occurs
- admin security checks remain enforced
- deployment env validation is performed in the target environment

## Known blocked areas
- live browser E2E is not fully exercised in this environment
- production deployment was not executed against a live host
- email delivery and TLS configuration require external runtime settings
