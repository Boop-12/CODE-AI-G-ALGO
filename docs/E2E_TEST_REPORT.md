# End-to-End Test Report

## Status
Blocked / not fully verified in this environment.

## Why
The repository contains a working frontend and backend, and both pass local compile/test validation, but no browser session was launched against a running app instance to exercise full end-to-end journeys.

## Planned smoke scenarios
1. Public homepage loads and keeps the original GNK logo
2. `/login`, `/register`, `/forgot-password`, `/reset-password`, and `/verify-email` routes render
3. User registration creates a test account and returns the expected email verification flow
4. Login succeeds with correct credentials and denies invalid ones
5. Dashboard loads after authentication and displays portfolio data
6. Admin login requires MFA and denies unauthorized users
7. Responsive layout holds at mobile, tablet, and desktop widths
8. Browser console shows no critical runtime errors

## Execution note
The application is ready for browser automation once a local or staging instance is started and reachable. The current validation evidence is static and backend-driven, not browser-driven.

## Residual risk
Without browser automation, certain UI regressions, route mismatches, and hydration issues could go unnoticed.

## Recommendation
Run the Playwright suite against a local Docker stack or a dedicated staging session before marking the project ready for public deployment.
