# Indian Markets and Broker Integration Foundation

## Current scope

This phase adds an adapter boundary and an isolated mock integration only. It does not connect to a broker, use external market data, submit live orders, or represent an exchange-certified instrument master.

| Area | Implemented development scope | Not implemented |
| --- | --- | --- |
| Provider | GNK mock paper broker | Zerodha, Dhan, FYERS |
| Exchanges | NSE and BSE identifiers in mock instruments and paper orders | Broker-specific exchange/product availability |
| Instruments | A small deterministic catalog of equities and two ETF examples | Complete/current security master, corporate actions, derivatives, commodities, currencies |
| Quotes | Fixed demonstration prices in INR | Real-time, delayed, or licensed market data |
| Orders | Existing manually submitted and manually filled paper orders, with NSE as the backward-compatible default and BSE selectable | Broker order placement, automated execution, market-hours or holiday enforcement |
| Account synchronization | Read-only mirror of the current user's paper ledger: summary, holdings/positions, and local paper-order statuses | Importing/reconciling any external broker account |
| Credentials | No mock credential or access token is collected or stored | Production OAuth/API credentials and external authorization callbacks |

Mock exchange instrument IDs are stable identifiers for this small development catalog only. They must not be treated as broker instrument tokens or as a current NSE/BSE instrument master. Both exchanges use fixed mock prices; they are not live quotes. Prices are represented as INR decimals with two fractional digits, quantities as whole shares, and the current paper order limit remains 1,000 shares. The current risk limits, manual fill flow, and short-sale restrictions remain in force.

The session endpoint reports the conventional NSE/BSE cash-session window (09:15–15:30 Asia/Kolkata) on weekdays for display only. No holiday calendar is loaded, and paper orders do not enforce market-session status. Verify the current official exchange calendar and broker-specific rules before relying on these values.

## Architecture

- `backend/app/brokers.py` defines provider-neutral capability, instrument, health, account, position, and order-status models, plus the `BrokerAdapter` protocol.
- The `MockBroker` implementation supplies deterministic quotes and a local eight-hour authorization lease. It cannot place orders (`order_placement=false`).
- `BrokerConnection` is scoped by user and provider. It stores connection state, expiry, and sync/health timestamps. Its optional token column is encrypted-only storage for future adapters; the mock adapter leaves it empty.
- Sensitive-value encryption reuses the existing Fernet construction derived from the server-side `SECRET_KEY`. Real credentials must never be put in source, frontend code, URLs, logs, or API responses. Production must use a strong, protected secret and an operational key-rotation/recovery plan.
- Broker snapshots are read-only projections from the authenticated user's paper account. Sync records an outcome and timestamp and emits an audit event; it does not import or alter orders/positions. Repeating sync does not create duplicate data.
- Rate-limit errors on adapter reads receive at most three attempts with bounded delay. Authorization errors are not retried; an expired mock lease disables paper orders until reconnect.

The database migration is additive for existing records. It adds exchange columns with `NSE` as the legacy default, expands position uniqueness to `(user, exchange, symbol)`, and creates broker connection records. Downgrade refuses to discard broker connections or BSE paper records.

## API surfaces

Authenticated endpoints:

- `GET /api/v1/settings/brokers` — mock availability, future-provider availability, connection and sync status.
- `POST /api/v1/broker/connect` with `{"provider":"mock"}` — local mock authorization; no credentials are accepted.
- `GET /api/v1/broker/health`, `POST /api/v1/broker/disconnect`, and `POST /api/v1/broker/sync`.
- `GET /api/v1/broker/account`, `/holdings`, `/positions`, and `/orders`.
- `GET /api/v1/instruments?exchange=NSE|BSE` — deterministic mock catalog and exchange-specific demo identifiers.
- `GET /api/v1/market/session` — informational session window; no holiday adjustment or order enforcement.
- Paper order requests accept an optional `exchange` (`NSE` or `BSE`); omitted exchange continues to mean NSE.

The Zerodha, Dhan, and FYERS entries are informational and unavailable. Their APIs must not be inferred from this interface. A future adapter requires a separately reviewed implementation against current official provider documentation, including authorization/state validation, token lifetimes and revocation, capabilities, product constraints, order idempotency, rate limits, data mapping, and provider terms.

## Later review gates

Before enabling a real provider or live trading, separately verify provider approval and API terms, exchange/data licensing, applicable Indian legal/regulatory obligations, and security/operational controls with qualified owners. Review secret-manager-backed encryption keys, rotation and incident recovery, callback/CSRF protections, idempotent order handling, audit retention, monitoring, and reconciliation policy. No compliance determination is made here.

## Validation

The backend platform tests cover NSE/BSE paper positions, mock connection and expiry, tenant isolation, repeatable read-only synchronization, encrypted token primitives, and bounded rate-limit handling. The existing browser suite should be run after the production frontend build to validate the account portal and paper-order UX.
