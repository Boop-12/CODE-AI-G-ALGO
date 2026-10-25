import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.broker_providers import BrokerProviderError, ProviderSnapshot, PROVIDERS
from app.core.config import settings
from app.core.security import decrypt_broker_token, encrypt_broker_token
from app.db.session import get_db
from app.models import AuditLog, BrokerAuthorizationAttempt, BrokerConnection, User


router = APIRouter()
ProviderId = Literal["zerodha", "dhan", "fyers"]
STATE_COOKIE_PREFIX = "gnk_broker_state_"
STATE_TTL = timedelta(minutes=10)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _state_hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _require_production(provider: str) -> None:
    if settings.ENVIRONMENT != "production":
        raise HTTPException(404, f"{provider.title()} integrations are available only in production")


def _snapshot_json(snapshot: ProviderSnapshot) -> dict:
    def decimal_strings(value):
        if isinstance(value, Decimal):
            return format(value, "f")
        if isinstance(value, dict):
            return {key: decimal_strings(item) for key, item in value.items()}
        if isinstance(value, list):
            return [decimal_strings(item) for item in value]
        return value

    return {
        "provider": snapshot.provider,
        "fetched_at": snapshot.fetched_at,
        "account": decimal_strings(snapshot.account.model_dump()),
        "holdings": decimal_strings([item.model_dump() for item in snapshot.holdings]),
        "positions": decimal_strings([item.model_dump() for item in snapshot.positions]),
        "orders": decimal_strings([item.model_dump() for item in snapshot.orders]),
    }


def _callback_redirect(provider: str, status: str) -> RedirectResponse:
    return RedirectResponse(
        f"{settings.APP_BASE_URL.rstrip('/')}/settings/brokers?provider={provider}&connection={status}",
        status_code=303,
    )


@router.post("/{provider}/connect")
async def begin_broker_authorization(
    provider: ProviderId,
    response: Response,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_production(provider)
    adapter = PROVIDERS[provider]
    if not adapter.configured():
        raise HTTPException(503, f"{provider.title()} production integration is not configured")
    state = secrets.token_urlsafe(32)
    try:
        authorization_url, provider_request_id = await adapter.begin_authorization(state)
    except BrokerProviderError as error:
        status = 429 if error.rate_limited else 503
        raise HTTPException(status, "Broker authorization could not be started") from None
    now = _now()
    await db.execute(delete(BrokerAuthorizationAttempt).where(or_(
        BrokerAuthorizationAttempt.expires_at < now,
        BrokerAuthorizationAttempt.consumed_at < now - timedelta(days=1),
    )))
    db.add(BrokerAuthorizationAttempt(
        state_hash=_state_hash(state),
        user_id=user.id,
        provider=provider,
        provider_request_id=provider_request_id,
        expires_at=now + STATE_TTL,
    ))
    await db.commit()
    response.set_cookie(
        f"{STATE_COOKIE_PREFIX}{provider}",
        state,
        max_age=int(STATE_TTL.total_seconds()),
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="lax",
        path=f"/api/v1/broker/callback/{provider}",
    )
    return {"provider": provider, "authorization_url": authorization_url}


@router.get("/callback/{provider}", name="broker_authorization_callback")
async def complete_broker_authorization(
    provider: ProviderId,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    _require_production(provider)
    query = dict(request.query_params)
    cookie_name = f"{STATE_COOKIE_PREFIX}{provider}"
    cookie_state = request.cookies.get(cookie_name, "")
    returned_state = query.get("state") or cookie_state
    if not cookie_state or not returned_state or not hmac.compare_digest(cookie_state, returned_state):
        raise HTTPException(400, "Broker authorization state is invalid or expired")
    attempt = (await db.execute(
        select(BrokerAuthorizationAttempt)
        .where(BrokerAuthorizationAttempt.state_hash == _state_hash(cookie_state))
        .with_for_update()
    )).scalar_one_or_none()
    if (
        not attempt
        or attempt.provider != provider
        or attempt.consumed_at is not None
        or _as_utc(attempt.expires_at) <= _now()
    ):
        raise HTTPException(400, "Broker authorization state is invalid or expired")
    attempt.consumed_at = _now()
    if query.get("error") or query.get("status", "success").lower() == "failure":
        await db.commit()
        redirect = _callback_redirect(provider, "cancelled")
        redirect.delete_cookie(cookie_name, path=f"/api/v1/broker/callback/{provider}", secure=settings.COOKIE_SECURE, httponly=True, samesite="lax")
        return redirect
    try:
        credentials = await PROVIDERS[provider].complete_authorization(query, attempt.provider_request_id)
        connection = (await db.execute(select(BrokerConnection).where(
            BrokerConnection.user_id == attempt.user_id,
            BrokerConnection.provider == provider,
        ))).scalar_one_or_none()
        if connection is None:
            connection = BrokerConnection(user_id=attempt.user_id, provider=provider)
            db.add(connection)
        connection.status = "connected"
        connection.account_label = credentials.account_label
        connection.provider_account_id = credentials.account_id
        connection.encrypted_access_token = encrypt_broker_token(credentials.access_token)
        connection.credential_expires_at = credentials.expires_at
        connection.last_sync_error = None
        connection.last_sync_status = None
        db.add(AuditLog(user_id=attempt.user_id, action="broker.connected", detail=provider))
        await db.commit()
    except BrokerProviderError as error:
        db.add(AuditLog(user_id=attempt.user_id, action="broker.authorization_failed", detail=f"{provider}:{error.code}"))
        await db.commit()
        redirect = _callback_redirect(provider, "failed")
        redirect.delete_cookie(cookie_name, path=f"/api/v1/broker/callback/{provider}", secure=settings.COOKIE_SECURE, httponly=True, samesite="lax")
        return redirect
    redirect = _callback_redirect(provider, "connected")
    redirect.delete_cookie(cookie_name, path=f"/api/v1/broker/callback/{provider}", secure=settings.COOKIE_SECURE, httponly=True, samesite="lax")
    return redirect


async def _connection(db: AsyncSession, user_id: uuid.UUID, provider: str) -> BrokerConnection:
    connection = (await db.execute(select(BrokerConnection).where(
        BrokerConnection.user_id == user_id,
        BrokerConnection.provider == provider,
    ))).scalar_one_or_none()
    if not connection or connection.status != "connected" or not connection.encrypted_access_token:
        raise HTTPException(409, "Connect this broker account first")
    if connection.credential_expires_at:
        expiry = connection.credential_expires_at
        expiry = expiry.replace(tzinfo=timezone.utc) if expiry.tzinfo is None else expiry.astimezone(timezone.utc)
        if expiry <= _now():
            connection.status = "expired"
            connection.last_sync_status = "expired"
            connection.last_sync_error = "authorization_expired"
            connection.encrypted_access_token = None
            db.add(AuditLog(user_id=user_id, action="broker.authorization_expired", detail=provider))
            await db.commit()
            raise HTTPException(409, "Broker authorization expired; reconnect the account")
    return connection


@router.get("/{provider}/health")
async def broker_connection_health(
    provider: ProviderId,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_production(provider)
    if not PROVIDERS[provider].configured():
        raise HTTPException(503, f"{provider.title()} production integration is not configured")
    connection = await _connection(db, user.id, provider)
    token = decrypt_broker_token(connection.encrypted_access_token or "")
    try:
        checked_at = await PROVIDERS[provider].health(token, connection.provider_account_id)
    except BrokerProviderError as error:
        if error.authorization_expired:
            connection.status = "expired"
            connection.encrypted_access_token = None
            connection.last_sync_status = "expired"
            db.add(AuditLog(user_id=user.id, action="broker.authorization_expired", detail=provider))
        connection.last_health_check_at = _now()
        connection.last_sync_error = error.code
        await db.commit()
        raise HTTPException(409 if error.authorization_expired else (429 if error.rate_limited else 503),
                            "Broker connection is expired" if error.authorization_expired else "Broker health check failed") from None
    connection.last_health_check_at = checked_at
    connection.last_sync_error = None
    await db.commit()
    return {"provider": provider, "status": "connected", "checked_at": checked_at}


@router.post("/{provider}/sync")
async def synchronize_broker(
    provider: ProviderId,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_production(provider)
    if not PROVIDERS[provider].configured():
        raise HTTPException(503, f"{provider.title()} production integration is not configured")
    connection = await _connection(db, user.id, provider)
    token = decrypt_broker_token(connection.encrypted_access_token or "")
    try:
        snapshot = await PROVIDERS[provider].snapshot(token, connection.provider_account_id)
    except BrokerProviderError as error:
        connection.last_synced_at = _now()
        connection.last_sync_status = "expired" if error.authorization_expired else "error"
        connection.last_sync_error = error.code
        if error.authorization_expired:
            connection.status = "expired"
            connection.encrypted_access_token = None
            db.add(AuditLog(user_id=user.id, action="broker.authorization_expired", detail=provider))
        await db.commit()
        raise HTTPException(409 if error.authorization_expired else (429 if error.rate_limited else 503),
                            "Broker authorization expired; reconnect the account" if error.authorization_expired else "Broker synchronization failed") from None
    connection.last_synced_at = snapshot.fetched_at
    connection.last_sync_status = "success"
    connection.last_sync_error = None
    db.add(AuditLog(user_id=user.id, action="broker.sync.completed", detail=provider))
    await db.commit()
    return _snapshot_json(snapshot) | {"sync_status": "success"}


@router.post("/{provider}/disconnect")
async def disconnect_broker(
    provider: ProviderId,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    connection = (await db.execute(select(BrokerConnection).where(
        BrokerConnection.user_id == user.id,
        BrokerConnection.provider == provider,
    ))).scalar_one_or_none()
    if connection:
        connection.status = "disconnected"
        connection.encrypted_access_token = None
        connection.credential_expires_at = None
        connection.provider_account_id = None
        connection.last_sync_error = None
    db.add(AuditLog(user_id=user.id, action="broker.disconnected", detail=f"{provider}:local_token_deleted"))
    await db.commit()
    return {"provider": provider, "status": "disconnected", "local_token_deleted": True, "provider_session_revoked": False}
