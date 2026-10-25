"""Provider-neutral models and the development-only paper broker."""
import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Callable, Mapping, Protocol, TypeVar

from fastapi import HTTPException

QUOTES = {
    "RELIANCE": {"name": "Reliance Industries", "price": "2952.40", "change": 0.84, "sector": "Energy"},
    "TCS": {"name": "Tata Consultancy Services", "price": "4125.65", "change": -0.32, "sector": "Technology"},
    "HDFCBANK": {"name": "HDFC Bank", "price": "1728.30", "change": 1.12, "sector": "Banking"},
    "INFY": {"name": "Infosys", "price": "1892.15", "change": 0.67, "sector": "Technology"},
    "ICICIBANK": {"name": "ICICI Bank", "price": "1254.80", "change": 0.92, "sector": "Banking"},
    "ITC": {"name": "ITC Limited", "price": "486.25", "change": -0.41, "sector": "Consumer goods"},
    "NIFTYBEES": {"name": "Nippon India ETF Nifty 50", "price": "275.40", "change": 0.52, "sector": "ETF"},
    "GOLDBEES": {"name": "Nippon India ETF Gold BeES", "price": "91.28", "change": 0.31, "sector": "ETF"},
}


@dataclass(frozen=True)
class BrokerCapabilities:
    exchanges: tuple[str, ...]
    segments: tuple[str, ...]
    account_summary: bool
    holdings: bool
    positions: bool
    order_status: bool
    order_placement: bool
    authorization_flow: str


@dataclass(frozen=True)
class IndianInstrument:
    exchange: str
    exchange_instrument_id: str
    symbol: str
    name: str
    asset_class: str
    currency: str
    price_precision: int
    quantity_precision: int
    quote: Decimal


def _instrument_id(exchange: str, symbol: str) -> str:
    bse_codes = {
        "RELIANCE": "500325", "TCS": "532540", "HDFCBANK": "500180",
        "INFY": "500209", "ICICIBANK": "532174", "ITC": "500875",
        "NIFTYBEES": "590103", "GOLDBEES": "590095",
    }
    return f"{symbol}" if exchange == "NSE" else bse_codes[symbol]


INSTRUMENTS = tuple(
    IndianInstrument(
        exchange=exchange,
        exchange_instrument_id=_instrument_id(exchange, symbol),
        symbol=symbol,
        name=quote["name"],
        asset_class="ETF" if quote["sector"] == "ETF" else "EQUITY",
        currency="INR",
        price_precision=2,
        quantity_precision=0,
        quote=Decimal(quote["price"]),
    )
    for exchange in ("NSE", "BSE")
    for symbol, quote in QUOTES.items()
)
INSTRUMENTS_BY_KEY = {(instrument.exchange, instrument.symbol): instrument for instrument in INSTRUMENTS}


@dataclass(frozen=True)
class BrokerAccountSummary:
    currency: str
    cash: Decimal
    equity: Decimal
    invested: Decimal


@dataclass(frozen=True)
class BrokerPosition:
    exchange: str
    exchange_instrument_id: str
    symbol: str
    quantity: int
    average_price: Decimal
    last_price: Decimal
    unrealized_pnl: Decimal


@dataclass(frozen=True)
class BrokerOrderStatus:
    order_id: str
    exchange: str
    exchange_instrument_id: str
    symbol: str
    side: str
    quantity: int
    status: str
    updated_at: datetime


@dataclass(frozen=True)
class BrokerHealth:
    status: str
    checked_at: datetime
    expires_at: datetime | None


@dataclass(frozen=True)
class AuthorizationRequest:
    authorization_url: str | None
    state: str | None
    expires_at: datetime


class BrokerRateLimitError(Exception):
    def __init__(self, retry_after_seconds: float = 0.01):
        self.retry_after_seconds = retry_after_seconds


class BrokerAuthorizationError(Exception):
    pass


class BrokerAdapter(Protocol):
    provider_id: str
    capabilities: BrokerCapabilities

    def begin_authorization(self, state: str, callback_url: str) -> AuthorizationRequest: ...
    def complete_authorization(self, callback: Mapping[str, str], expected_state: str) -> datetime: ...
    def authorize(self) -> datetime: ...
    def health(self, expires_at: datetime | None, now: datetime) -> BrokerHealth: ...
    def account_summary(self, cash: Decimal, positions: list[BrokerPosition]) -> BrokerAccountSummary: ...
    def holdings(self, positions: list[BrokerPosition]) -> list[BrokerPosition]: ...
    def positions(self, positions: list[BrokerPosition]) -> list[BrokerPosition]: ...
    def order_status(self, orders: list[BrokerOrderStatus]) -> list[BrokerOrderStatus]: ...
    def disconnect(self) -> None: ...
    def quote(self, symbol: str) -> Decimal: ...


STRATEGIES = [
    {"id": "momentum", "name": "Momentum Compass", "category": "Trend following", "risk": "Moderate", "description": "Explore momentum in a simulated equity basket. Orders are entered manually; automated signals are not enabled.", "instruments": "NSE equities", "color": "green"},
    {"id": "mean-reversion", "name": "Mean Reversion", "category": "Range trading", "risk": "High", "description": "A template for studying deviations from an average. No historical returns or live execution are claimed.", "instruments": "NSE equities", "color": "blue"},
    {"id": "balanced", "name": "Balanced Basket", "category": "Portfolio", "risk": "Moderate", "description": "Practice allocation in a paper portfolio. Activation saves configuration; automatic execution is not enabled.", "instruments": "NSE equities", "color": "amber"},
]

class BrokerAdapter(Protocol):
    mode: str
    def quote(self, symbol: str) -> Decimal: ...

class MockBroker:
    provider_id = "mock"
    mode = "paper"
    capabilities = BrokerCapabilities(
        exchanges=("NSE", "BSE"),
        segments=("EQUITY", "ETF"),
        account_summary=True,
        holdings=True,
        positions=True,
        order_status=True,
        order_placement=False,
        authorization_flow="local_mock",
    )

    def __init__(self):
        self.rate_limit_failures = 0
        self.rate_limit_attempts = 0

    def _check_rate_limit(self) -> None:
        self.rate_limit_attempts += 1
        if self.rate_limit_failures:
            self.rate_limit_failures -= 1
            raise BrokerRateLimitError()

    def authorize(self) -> datetime:
        self._check_rate_limit()
        return datetime.now(timezone.utc) + timedelta(hours=8)

    def begin_authorization(self, state: str, callback_url: str) -> AuthorizationRequest:
        del state, callback_url
        return AuthorizationRequest(None, None, self.authorize())

    def complete_authorization(self, callback: Mapping[str, str], expected_state: str) -> datetime:
        del callback, expected_state
        raise BrokerAuthorizationError("The mock broker does not use an external callback")

    def health(self, expires_at: datetime | None, now: datetime) -> BrokerHealth:
        self._check_rate_limit()
        if expires_at is not None:
            normalized_expiry = expires_at.replace(tzinfo=timezone.utc) if expires_at.tzinfo is None else expires_at.astimezone(timezone.utc)
            if normalized_expiry <= now:
                raise BrokerAuthorizationError("Mock broker authorization has expired")
        return BrokerHealth("connected", now, expires_at)

    def account_summary(self, cash: Decimal, positions: list[BrokerPosition]) -> BrokerAccountSummary:
        self._check_rate_limit()
        invested = sum((position.last_price * position.quantity for position in positions), Decimal(0))
        return BrokerAccountSummary("INR", cash, cash + invested, invested)

    def holdings(self, positions: list[BrokerPosition]) -> list[BrokerPosition]:
        self._check_rate_limit()
        return positions

    def positions(self, positions: list[BrokerPosition]) -> list[BrokerPosition]:
        self._check_rate_limit()
        return positions

    def order_status(self, orders: list[BrokerOrderStatus]) -> list[BrokerOrderStatus]:
        self._check_rate_limit()
        return orders

    def disconnect(self) -> None:
        self._check_rate_limit()

    def quote(self, symbol: str) -> Decimal:
        return Decimal(QUOTES[symbol]["price"])


T = TypeVar("T")


async def bounded_broker_read(operation: Callable[[], T], attempts: int = 3) -> T:
    """Retry only rate-limited reads, with a small bounded exponential delay."""
    for attempt in range(attempts):
        try:
            return operation()
        except BrokerRateLimitError as exc:
            if attempt + 1 == attempts:
                raise HTTPException(429, "Mock broker rate limit reached; retry shortly") from exc
            await asyncio.sleep(min(exc.retry_after_seconds * (2 ** attempt), 0.05))
    raise RuntimeError("Broker retry loop ended unexpectedly")


mock_broker = MockBroker()
broker: BrokerAdapter = mock_broker
