# Indian Broker Integrations

## Production scope

The production broker connections are server-side and read-only. They retrieve account summaries, holdings, positions, and order statuses. They do not submit, modify, or cancel live orders, and they are separate from the existing paper-trading workflow. The mock adapter remains for development; production settings expose only Zerodha, Dhan, and FYERS.

Provider availability depends on the matching server-side credentials. No broker credential or access token is collected by the frontend. Oracle remains out of scope until its exact brokerage product and official API documentation are identified.

| Provider | Authorization | Read-only data | Expiry handling |
| --- | --- | --- | --- |
| Zerodha | Kite Connect request-token exchange and checksum | Profile, margins, holdings, positions, order book | Persisted expiry at 06:00 Asia/Kolkata on the next calendar day; provider authorization errors expire the connection |
| Dhan | Partner consent flow and token exchange | Fund limits, holdings, positions, order book | Uses the provider-returned `expiryTime`; timezone offsets are preserved, and offset-free timestamps are interpreted as Asia/Kolkata |
| FYERS | API v3 authorization-code exchange | Profile, funds, holdings, positions, order book | Provider response does not currently supply an expiry in this adapter; authorization failures mark it expired and require reconnection |

The FYERS flow and read operations follow the official [FYERS API v3 sample repository](https://github.com/FyersDev/fyers-api-sample-code) and SDK method conventions. Reconfirm current provider docs, app approval, callback configuration, and account permissions before production use.

## Data and market boundaries

The adapters return provider-neutral account, holding, position, and order-status snapshots. Each record retains the provider's exchange and exchange-specific identifier where available; unknown values are not inferred as instrument-master data. Monetary values are represented as decimals, quantities as integers, and currency as INR where the provider response supports that interpretation.

This is not a complete NSE/BSE security master or a market-data feed. It does not claim end-to-end market support, real-time prices, licensed quotes, derivatives, order eligibility, holiday enforcement, or uniform exchange/product capability across brokers. The initial data view is account and portfolio read-only. Consult current provider documentation for actual instruments, segments, and account permissions.

## Security and lifecycle

- OAuth state is cryptographically random, stored only as a hash, tied to the initiating tenant, expires after ten minutes, and is consumed once. A provider-specific HttpOnly, SameSite=Lax cookie binds the callback to that browser.
- Provider requests and token exchanges run only on the backend. Access tokens are encrypted with Fernet using a dedicated server key (`BROKER_TOKEN_ENCRYPTION_KEY`) and are never returned by an API.
- Production logs omit request query strings on broker callbacks. Uvicorn access logging is disabled in the production Compose overlay because callbacks contain short-lived authorization parameters.
- Provider GET requests use bounded timeouts, at most three attempts, and capped backoff for transient errors and rate limits. Authorization failures are not retried. Authorization/token-exchange POST requests are never retried.
- An expired or rejected token is marked expired, removed from local encrypted storage, audited, and requires reconnection. Health checks call a provider read endpoint; they do not treat an unverified token as healthy.
- Disconnect deletes the locally stored token and account link and records an audit event. This release does not call a provider-side revoke endpoint for Dhan or FYERS; users must revoke the app from their broker account when required. Zerodha supports a provider logout endpoint, but remote revocation is not yet wired into this release.
- Synchronization is on-demand and repeatable. It returns a fresh read-only snapshot and stores only health/sync timestamps and outcome, not broker portfolio rows. There are no duplicate imported rows or automatic reconciliation writes. Compare provider snapshots with broker statements and report discrepancies through an operational reconciliation process.

## Production setup

1. Obtain the required provider application approval and production credentials through each broker's official process. Dhan uses partner credentials for this platform flow.
2. Add the listed values to the production server's protected `.env` or secret manager. Do not paste credentials into chat, frontend variables, source control, or logs.
3. Generate a dedicated Fernet key with a trusted secret-management process and set `BROKER_TOKEN_ENCRYPTION_KEY`. Keep it stable and backed up securely; losing or rotating it without re-encrypting stored tokens makes existing connections unusable.
4. Register these exact HTTPS callback URLs with the corresponding provider application:
   - `https://gnkalgo.com/api/v1/broker/callback/zerodha`
   - `https://gnkalgo.com/api/v1/broker/callback/dhan`
   - `https://gnkalgo.com/api/v1/broker/callback/fyers`
5. Set the provider credentials in pairs. Supported variable names are documented without values in [`.env.production.example`](../.env.production.example). A provider is shown as available only when its complete credential pair is configured.
6. Back up the database, deploy the image, and allow the production migration service to apply additive migrations. Do not reset the database.
7. Sign in, open **Settings → Brokers**, choose **Connect account**, and complete the broker's own authorization/2FA page. Then use **Check health** or **Sync account data**.
8. Test authorization cancellation, expiry, disconnect, and provider rate-limit handling with approved test accounts before enabling access to production users.

## Operational and compliance gates

Before enabling each provider, verify current provider terms, API approval, OAuth redirect registration, user consent, security controls, and supported account endpoints with the provider. Review broker contract rules, exchange/data licensing, record retention, and Indian legal, regulatory, and tax obligations with qualified owners. This document is not a compliance determination. Do not enable live order placement without a separate approved implementation, provider-specific documentation review, safeguards, and test plan.

## Official references

- [Kite Connect v3 user and session APIs](https://kite.trade/docs/connect/v3/user/)
- [DhanHQ v2 authentication](https://dhanhq.co/docs/v2/authentication/)
- [FYERS API v3 sample code](https://github.com/FyersDev/fyers-api-sample-code)