"""Production broker authorization and read-only portfolio adapters."""
import asyncio
import hashlib
import hmac
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Literal, Mapping
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.core.config import settings


class BrokerProviderError(Exception):
    def __init__(self, code: str, *, authorization_expired: bool = False, rate_limited: bool = False):
        super().__init__(code)
        self.code = code
        self.authorization_expired = authorization_expired
        self.rate_limited = rate_limited


@dataclass(frozen=True)
class ProviderTokens:
    access_token: str
    expires_at: datetime | None
    account_id: str | None
    account_label: str


@dataclass(frozen=True)
class BrokerCapabilities:
    account_summary: bool
    holdings: bool
    positions: bool
    order_status: bool
    order_placement: bool = False
    provider_revocation: bool = False


class BrokerAccountSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: str | None = None
    account_name: str | None = None
    currency: str = "INR"
    available_balance: Decimal
    equity: Decimal | None = None
    withdrawable_balance: Decimal | None = None
    utilized_amount: Decimal | None = None


class BrokerInstrumentSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    exchange: str | None = None
    exchange_segment: str | None = None
    exchange_instrument_id: str | None = None
    symbol: str | None = None
    isin: str | None = None
    quantity: int
    average_price: Decimal | None = None
    last_price: Decimal | None = None
    currency: str = "INR"
    unrealized_pnl: Decimal | None = None
    realized_pnl: Decimal | None = None


class BrokerOrderStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order_id: str = Field(min_length=1)
    exchange: str | None = None
    exchange_segment: str | None = None
    exchange_instrument_id: str | None = None
    symbol: str | None = None
    side: str | None = None
    quantity: int
    status: str | None = None
    updated_at: datetime | str | None = None


class ProviderSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: Literal["zerodha", "dhan", "fyers"]
    account: BrokerAccountSnapshot
    holdings: list[BrokerInstrumentSnapshot]
    positions: list[BrokerInstrumentSnapshot]
    orders: list[BrokerOrderStatus]
    fetched_at: datetime


def _snapshot(**values: Any) -> ProviderSnapshot:
    try:
        return ProviderSnapshot(**values)
    except ValidationError:
        raise BrokerProviderError("provider_invalid_response") from None


def _decimal(value: Any) -> Decimal:
    if value is None or value == "":
        return Decimal(0)
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise BrokerProviderError("provider_invalid_response") from None
    if not result.is_finite():
        raise BrokerProviderError("provider_invalid_response")
    return result


def _int(value: Any) -> int:
    if value is None or value == "":
        return 0
    try:
        return int(value)
    except (ValueError, TypeError, OverflowError):
        raise BrokerProviderError("provider_invalid_response") from None


def _dict(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise BrokerProviderError("provider_invalid_response")
    return value


def _list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise BrokerProviderError("provider_invalid_response")
    return value


async def _request_json(
    method: str,
    url: str,
    *,
    headers: Mapping[str, str] | None = None,
    params: Mapping[str, str] | None = None,
    data: Mapping[str, str] | None = None,
    json: Mapping[str, Any] | None = None,
) -> Any:
    retryable = method.upper() == "GET"
    timeout = httpx.Timeout(settings.BROKER_HTTP_TIMEOUT_SECONDS, connect=min(5.0, settings.BROKER_HTTP_TIMEOUT_SECONDS))
    for attempt in range(3 if retryable else 1):
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
                response = await client.request(method, url, headers=headers, params=params, data=data, json=json)
        except httpx.TimeoutException:
            if retryable and attempt < 2:
                await asyncio.sleep(0.1 * (2 ** attempt))
                continue
            raise BrokerProviderError("provider_timeout") from None
        except httpx.RequestError:
            if retryable and attempt < 2:
                await asyncio.sleep(0.1 * (2 ** attempt))
                continue
            raise BrokerProviderError("provider_unavailable") from None

        if response.status_code == 429:
            if retryable and attempt < 2:
                retry_after = response.headers.get("Retry-After", "")
                try:
                    delay = min(max(float(retry_after), 0.0), 2.0)
                except ValueError:
                    delay = 0.1 * (2 ** attempt)
                await asyncio.sleep(delay)
                continue
            raise BrokerProviderError("provider_rate_limited", rate_limited=True)
        if response.status_code in (401, 403):
            raise BrokerProviderError("provider_authorization_expired", authorization_expired=True)
        if response.status_code >= 500:
            if retryable and attempt < 2:
                await asyncio.sleep(0.1 * (2 ** attempt))
                continue
            raise BrokerProviderError("provider_temporarily_unavailable")
        if response.status_code >= 400:
            raise BrokerProviderError("provider_request_rejected")
        try:
            payload = response.json()
        except ValueError:
            raise BrokerProviderError("provider_invalid_response") from None

        if isinstance(payload, dict):
            provider_status = str(payload.get("status", payload.get("s", ""))).lower()
            provider_error_code = str(payload.get("errorCode", "")).lower()
            has_provider_error = provider_status in {"error", "failed", "failure"} or (
                provider_error_code not in {"", "0", "none"}
            )
            if has_provider_error:
                code = str(
                    payload.get("error_type")
                    or payload.get("code")
                    or payload.get("errorMessage")
                    or payload.get("message")
                    or payload.get("remarks")
                    or ""
                ).lower()
                if "token" in code or "auth" in code or "session" in code:
                    raise BrokerProviderError("provider_authorization_expired", authorization_expired=True)
                raise BrokerProviderError("provider_request_rejected")
        return payload
    raise BrokerProviderError("provider_temporarily_unavailable")


class BrokerProvider:
    provider_id: str
    capabilities: BrokerCapabilities

    def configured(self) -> bool:
        raise NotImplementedError

    def callback_url(self) -> str:
        return f"{settings.APP_BASE_URL.rstrip('/')}/api/v1/broker/callback/{self.provider_id}"

    async def begin_authorization(self, state: str) -> tuple[str, str | None]:
        raise NotImplementedError

    async def complete_authorization(self, query: Mapping[str, str], provider_request_id: str | None) -> ProviderTokens:
        raise NotImplementedError

    async def snapshot(self, access_token: str, account_id: str | None) -> ProviderSnapshot:
        raise NotImplementedError

    async def health(self, access_token: str, account_id: str | None) -> datetime:
        raise NotImplementedError

    async def disconnect(self, access_token: str, account_id: str | None) -> bool:
        del access_token, account_id
        return False


class ZerodhaProvider(BrokerProvider):
    provider_id = "zerodha"
    capabilities = BrokerCapabilities(True, True, True, True)
    _api_root = "https://api.kite.trade"
    _login_root = "https://kite.zerodha.com/connect/login"

    def configured(self) -> bool:
        return bool(settings.ZERODHA_API_KEY and settings.ZERODHA_API_SECRET)

    async def begin_authorization(self, state: str) -> tuple[str, str | None]:
        if not self.configured():
            raise BrokerProviderError("provider_not_configured")
        redirect_params = urlencode({"state": state})
        return f"{self._login_root}?{urlencode({'v': '3', 'api_key': settings.ZERODHA_API_KEY, 'redirect_params': redirect_params})}", None

    async def complete_authorization(self, query: Mapping[str, str], provider_request_id: str | None) -> ProviderTokens:
        del provider_request_id
        request_token = query.get("request_token", "")
        if not request_token or query.get("status", "success").lower() != "success":
            raise BrokerProviderError("provider_authorization_cancelled")
        api_key = settings.ZERODHA_API_KEY or ""
        api_secret = settings.ZERODHA_API_SECRET or ""
        checksum = hashlib.sha256(f"{api_key}{request_token}{api_secret}".encode()).hexdigest()
        payload = _dict(await _request_json(
            "POST",
            f"{self._api_root}/session/token",
            headers={"X-Kite-Version": "3"},
            data={"api_key": api_key, "request_token": request_token, "checksum": checksum},
        ))
        data = _dict(payload.get("data"))
        access_token = data.get("access_token")
        if payload.get("status") != "success" or not isinstance(access_token, str) or not access_token:
            raise BrokerProviderError("provider_authorization_failed")
        now_ist = datetime.now(ZoneInfo("Asia/Kolkata"))
        expiry = (now_ist + timedelta(days=1)).replace(hour=6, minute=0, second=0, microsecond=0)
        return ProviderTokens(
            access_token=access_token,
            expires_at=expiry.astimezone(timezone.utc),
            account_id=str(data.get("user_id") or "") or None,
            account_label="Zerodha account",
        )

    async def _get(self, path: str, token: str) -> Any:
        return await _request_json(
            "GET",
            f"{self._api_root}{path}",
            headers={"X-Kite-Version": "3", "Authorization": f"token {settings.ZERODHA_API_KEY}:{token}"},
        )

    async def snapshot(self, access_token: str, account_id: str | None) -> ProviderSnapshot:
        del account_id
        profile, margins, holdings_result, positions_result, orders_result = await asyncio.gather(
            self._get("/user/profile", access_token),
            self._get("/user/margins", access_token),
            self._get("/portfolio/holdings", access_token),
            self._get("/portfolio/positions", access_token),
            self._get("/orders", access_token),
        )
        profile_data = _dict(_dict(profile).get("data"))
        margins_data = _dict(_dict(margins).get("data"))
        equity = _dict(margins_data.get("equity"))
        available = _dict(equity.get("available"))
        if "cash" not in available:
            raise BrokerProviderError("provider_invalid_response")
        net = _decimal(equity.get("net"))

        def normalize_position(item: dict[str, Any]) -> dict[str, Any]:
            return {
                "exchange": item.get("exchange"),
                "exchange_instrument_id": str(item.get("instrument_token") or ""),
                "symbol": item.get("tradingsymbol"),
                "isin": item.get("isin"),
                "quantity": _int(item.get("quantity")),
                "average_price": _decimal(item.get("average_price")),
                "last_price": _decimal(item.get("last_price")),
                "currency": "INR",
            }

        positions = _dict(_dict(positions_result).get("data"))
        return _snapshot(
            provider=self.provider_id,
            account={
                "account_id": profile_data.get("user_id"),
                "account_name": profile_data.get("user_name"),
                "currency": "INR",
                "available_balance": _decimal(available.get("cash")),
                "equity": net,
            },
            holdings=[normalize_position(item) for item in _list(_dict(holdings_result).get("data"))],
            positions=[normalize_position(item) for item in _list(positions.get("net")) if _int(item.get("quantity")) != 0],
            orders=[{
                "order_id": str(item.get("order_id") or ""),
                "exchange": item.get("exchange"),
                "symbol": item.get("tradingsymbol"),
                "side": item.get("transaction_type"),
                "quantity": _int(item.get("quantity")),
                "status": item.get("status"),
                "updated_at": item.get("order_timestamp") or item.get("exchange_update_timestamp"),
            } for item in _list(_dict(orders_result).get("data"))],
            fetched_at=datetime.now(timezone.utc),
        )

    async def health(self, access_token: str, account_id: str | None) -> datetime:
        del account_id
        await self._get("/user/profile", access_token)
        return datetime.now(timezone.utc)


class DhanProvider(BrokerProvider):
    provider_id = "dhan"
    capabilities = BrokerCapabilities(True, True, True, True)
    _auth_root = "https://auth.dhan.co"
    _api_root = "https://api.dhan.co/v2"

    def configured(self) -> bool:
        return bool(settings.DHAN_PARTNER_ID and settings.DHAN_PARTNER_SECRET)

    async def begin_authorization(self, state: str) -> tuple[str, str | None]:
        del state
        if not self.configured():
            raise BrokerProviderError("provider_not_configured")
        result = _dict(await _request_json(
            "POST",
            f"{self._auth_root}/partner/generate-consent",
            headers={
                "partner_id": settings.DHAN_PARTNER_ID or "",
                "partner_secret": settings.DHAN_PARTNER_SECRET or "",
            },
        ))
        consent_id = result.get("consentId")
        if result.get("consentStatus") != "GENERATED" or not isinstance(consent_id, str):
            raise BrokerProviderError("provider_authorization_failed")
        return f"{self._auth_root}/consent-login?{urlencode({'consentId': consent_id})}", consent_id

    async def complete_authorization(self, query: Mapping[str, str], provider_request_id: str | None) -> ProviderTokens:
        del provider_request_id
        token_id = query.get("tokenId", "")
        if not token_id:
            raise BrokerProviderError("provider_authorization_cancelled")
        result = _dict(await _request_json(
            "POST",
            f"{self._auth_root}/partner/consume-consent",
            headers={
                "partner_id": settings.DHAN_PARTNER_ID or "",
                "partner_secret": settings.DHAN_PARTNER_SECRET or "",
            },
            params={"tokenId": token_id},
        ))
        token = result.get("accessToken")
        expiry = result.get("expiryTime")
        if not isinstance(token, str) or not token or not isinstance(expiry, str):
            raise BrokerProviderError("provider_authorization_failed")
        try:
            expires_at = datetime.fromisoformat(expiry)
        except ValueError:
            raise BrokerProviderError("provider_invalid_response") from None
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=ZoneInfo("Asia/Kolkata"))
        expires_at = expires_at.astimezone(timezone.utc)
        client_id = result.get("dhanClientId")
        return ProviderTokens(
            access_token=token,
            expires_at=expires_at,
            account_id=str(client_id or "") or None,
            account_label="Dhan account",
        )

    async def _get(self, path: str, token: str) -> Any:
        return await _request_json(
            "GET",
            f"{self._api_root}{path}",
            headers={"access-token": token, "Accept": "application/json"},
        )

    async def snapshot(self, access_token: str, account_id: str | None) -> ProviderSnapshot:
        fund_result, holdings_result, positions_result, orders_result = await asyncio.gather(
            self._get("/fundlimit", access_token),
            self._get("/holdings", access_token),
            self._get("/positions", access_token),
            self._get("/orders", access_token),
        )
        funds = _dict(fund_result)
        available_balance = funds.get("availableBalance", funds.get("availabelBalance"))
        if available_balance is None:
            raise BrokerProviderError("provider_invalid_response")

        def normalize(item: dict[str, Any], *, position: bool) -> dict[str, Any]:
            exchange_segment = str(item.get("exchangeSegment") or item.get("exchange") or "")
            exchange = "BSE" if exchange_segment.startswith("BSE") else "NSE" if exchange_segment.startswith("NSE") else None
            return {
                "exchange": exchange,
                "exchange_segment": exchange_segment or None,
                "exchange_instrument_id": str(item.get("securityId") or ""),
                "symbol": item.get("tradingSymbol"),
                "isin": item.get("isin"),
                "quantity": _int(item.get("netQty") if position else item.get("totalQty")),
                "average_price": _decimal(item.get("costPrice") if position else item.get("avgCostPrice")),
                "last_price": _decimal(item.get("ltp")),
                "unrealized_pnl": _decimal(item.get("unrealizedProfit")),
                "currency": "INR",
            }

        return _snapshot(
            provider=self.provider_id,
            account={
                "account_id": account_id,
                "currency": "INR",
                "available_balance": _decimal(available_balance),
                "withdrawable_balance": _decimal(funds.get("withdrawableBalance")),
                "utilized_amount": _decimal(funds.get("utilizedAmount")),
            },
            holdings=[normalize(item, position=False) for item in _list(holdings_result)],
            positions=[normalize(item, position=True) for item in _list(positions_result) if _int(item.get("netQty")) != 0],
            orders=[{
                "order_id": str(item.get("orderId") or ""),
                "exchange": "BSE" if str(item.get("exchangeSegment", "")).startswith("BSE") else "NSE",
                "exchange_segment": item.get("exchangeSegment"),
                "exchange_instrument_id": str(item.get("securityId") or ""),
                "symbol": item.get("tradingSymbol"),
                "side": item.get("transactionType"),
                "quantity": _int(item.get("quantity")),
                "status": item.get("orderStatus"),
                "updated_at": item.get("updateTime") or item.get("createTime"),
            } for item in _list(orders_result)],
            fetched_at=datetime.now(timezone.utc),
        )

    async def health(self, access_token: str, account_id: str | None) -> datetime:
        del account_id
        await self._get("/fundlimit", access_token)
        return datetime.now(timezone.utc)


class FyersProvider(BrokerProvider):
    provider_id = "fyers"
    capabilities = BrokerCapabilities(True, True, True, True)
    _api_root = "https://api-t1.fyers.in/api/v3"

    def configured(self) -> bool:
        return bool(settings.FYERS_APP_ID and settings.FYERS_SECRET_KEY)

    async def begin_authorization(self, state: str) -> tuple[str, str | None]:
        if not self.configured():
            raise BrokerProviderError("provider_not_configured")
        return f"{self._api_root}/generate-authcode?{urlencode({
            'client_id': settings.FYERS_APP_ID or '',
            'redirect_uri': self.callback_url(),
            'response_type': 'code',
            'state': state,
        })}", None

    async def complete_authorization(self, query: Mapping[str, str], provider_request_id: str | None) -> ProviderTokens:
        del provider_request_id
        auth_code = query.get("auth_code") or query.get("code")
        if not auth_code:
            raise BrokerProviderError("provider_authorization_cancelled")
        client_id = settings.FYERS_APP_ID or ""
        secret = settings.FYERS_SECRET_KEY or ""
        app_id_hash = hashlib.sha256(f"{client_id}:{secret}".encode()).hexdigest()
        result = _dict(await _request_json(
            "POST",
            f"{self._api_root}/validate-authcode",
            json={"grant_type": "authorization_code", "appIdHash": app_id_hash, "code": auth_code},
        ))
        access_token = result.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise BrokerProviderError("provider_authorization_failed")
        return ProviderTokens(
            access_token=access_token,
            expires_at=None,
            account_id=str(result.get("fy_id") or result.get("user_id") or "") or None,
            account_label="FYERS account",
        )

    async def _get(self, path: str, token: str) -> Any:
        return await _request_json(
            "GET",
            f"{self._api_root}{path}",
            headers={"Authorization": f"{settings.FYERS_APP_ID}:{token}"},
        )

    async def snapshot(self, access_token: str, account_id: str | None) -> ProviderSnapshot:
        profile_result, funds_result, holdings_result, positions_result, orders_result = await asyncio.gather(
            self._get("/profile", access_token),
            self._get("/funds", access_token),
            self._get("/holdings", access_token),
            self._get("/positions", access_token),
            self._get("/orders", access_token),
        )
        profile = _dict(_dict(profile_result).get("data"))
        funds_payload = _dict(funds_result)
        funds = _list(funds_payload.get("fund_limit"))
        balance_rows = [item for item in funds if item.get("title") == "Total Balance"]
        if not balance_rows or "equityAmount" not in balance_rows[0]:
            raise BrokerProviderError("provider_invalid_response")
        balance = _decimal(balance_rows[0].get("equityAmount"))

        def normalize(item: dict[str, Any]) -> dict[str, Any]:
            symbol = str(item.get("symbol") or item.get("symbolName") or "")
            exchange = "BSE" if symbol.startswith("BSE:") else "NSE" if symbol.startswith("NSE:") else None
            return {
                "exchange": exchange,
                "exchange_instrument_id": str(item.get("id") or ""),
                "symbol": symbol.split(":", 1)[-1] if ":" in symbol else symbol,
                "quantity": _int(item.get("qty", item.get("quantity"))),
                "average_price": _decimal(item.get("costPrice", item.get("avgPrice"))),
                "last_price": _decimal(item.get("ltp", item.get("lastPrice"))),
                "currency": "INR",
            }

        holding_rows = _list(_dict(holdings_result).get("data"))
        position_rows = _list(_dict(positions_result).get("data"))
        order_rows = _list(_dict(orders_result).get("data"))
        return _snapshot(
            provider=self.provider_id,
            account={
                "account_id": profile.get("fy_id") or account_id,
                "account_name": profile.get("name"),
                "currency": "INR",
                "available_balance": balance,
            },
            holdings=[normalize(item) for item in holding_rows],
            positions=[normalize(item) | {
                "unrealized_pnl": _decimal(item.get("pl")),
                "realized_pnl": _decimal(item.get("realized_profit")),
            } for item in position_rows],
            orders=[{
                "order_id": str(item.get("id") or ""),
                "exchange": "BSE" if str(item.get("symbol", "")).startswith("BSE:") else "NSE",
                "symbol": str(item.get("symbol") or "").split(":", 1)[-1],
                "side": item.get("side"),
                "quantity": _int(item.get("qty")),
                "status": item.get("status"),
                "updated_at": item.get("orderDateTime"),
            } for item in order_rows],
            fetched_at=datetime.now(timezone.utc),
        )

    async def health(self, access_token: str, account_id: str | None) -> datetime:
        del account_id
        await self._get("/profile", access_token)
        return datetime.now(timezone.utc)


PROVIDERS: dict[str, BrokerProvider] = {
    "zerodha": ZerodhaProvider(),
    "dhan": DhanProvider(),
    "fyers": FyersProvider(),
}
