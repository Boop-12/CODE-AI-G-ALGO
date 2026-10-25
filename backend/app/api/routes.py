import secrets
import uuid
from datetime import datetime, time as datetime_time, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo
from typing import Literal
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.api.deps import get_admin, get_current_user, locked_account
from app.brokers import (
    INSTRUMENTS,
    INSTRUMENTS_BY_KEY,
    QUOTES,
    STRATEGIES,
    BrokerAuthorizationError,
    BrokerOrderStatus,
    BrokerPosition,
    BrokerRateLimitError,
    bounded_broker_read,
    broker,
    mock_broker,
)
from app.core.config import settings
from app.core.security import get_password_hash, verify_password, hash_token, decrypt_mfa_secret, verify_totp, password_needs_rehash
from app.core.mailer import action_url, deliver_link
from app.db.session import get_db
from app.models import User, Account, BrokerConnection, Session, Deployment, Order, Position, AuditLog, SupportTicket, EmailVerificationToken, LoginHistory, SystemSetting

router = APIRouter()
MAX_EXPOSURE = Decimal("500000")
MAX_DAILY_LOSS = Decimal("10000")

def audit(db, user_id, action, detail=""):
    db.add(AuditLog(user_id=user_id, action=action, detail=detail))

def row(obj, fields):
    return {key: getattr(obj, key) for key in fields.split()}

def user_view(user):
    return {"id": str(user.id), "name": user.name, "email": user.email, "roles": [r.name for r in user.roles], "email_verified": user.email_verified, "theme": user.theme, "mfa_enabled": user.mfa_enabled}

class Register(BaseModel):
    name: str = Field(min_length=2, max_length=80, pattern=r"\S")
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)

class Login(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)
    mfa_code: str | None = Field(default=None, pattern=r"^\d{6}$")

async def start_session(db, response, user_id, request):
    token = secrets.token_urlsafe(48)
    db.add(Session(
        token_hash=hash_token(token),
        user_id=user_id,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=settings.SESSION_MINUTES),
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent", "")[:512] or None,
    ))
    response.set_cookie("gnk_session", token, httponly=True, secure=settings.COOKIE_SECURE, samesite="strict", max_age=settings.SESSION_MINUTES * 60, path="/api")

@router.post("/auth/register", status_code=201)
async def register(body: Register, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    registration = await db.get(SystemSetting, "registration_enabled")
    if registration and registration.value == "false":
        raise HTTPException(403, "New account registration is currently disabled")
    user = User(name=body.name.strip(), email=str(body.email).lower(), hashed_password=get_password_hash(body.password), email_verified=False)
    db.add(user)
    try:
        await db.flush()
        db.add(Account(user_id=user.id))
        await start_session(db, response, user.id, request)
        audit(db, user.id, "account.created", "INR 1,000,000 virtual capital")
        verification_token = secrets.token_urlsafe(32)
        db.add(EmailVerificationToken(
            user_id=user.id,
            token_hash=hash_token(verification_token),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        ))
        verification_url = action_url("verify-email", verification_token)
        delivered = await deliver_link(user.email, "Verify your GnkAlgo Trader email", f"Verify your email: {verification_url}")
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, "Unable to register this email")
    result = {"id": str(user.id), "name": user.name, "email": user.email, "roles": [], "email_verified": False, "theme": user.theme, "mfa_enabled": False, "verification_sent": delivered}
    if not delivered and settings.ENVIRONMENT != "production":
        result["development_verification_url"] = verification_url
    return result

@router.post("/auth/login")
async def login(body: Login, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    user = (await db.execute(select(User).options(selectinload(User.roles)).where(User.email == str(body.email).lower()))).scalar_one_or_none()
    valid = verify_password(body.password, user.hashed_password) if user else bool(get_password_hash(body.password)) and False
    if valid and user and user.mfa_enabled:
        valid = bool(body.mfa_code and user.mfa_secret and verify_totp(decrypt_mfa_secret(user.mfa_secret), body.mfa_code))
    if not user or not valid or not user.is_active:
        raise HTTPException(401, "Email or password is incorrect")
    if password_needs_rehash(user.hashed_password):
        user.hashed_password = get_password_hash(body.password)
    await start_session(db, response, user.id, request)
    db.add(LoginHistory(
        user_id=user.id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent", "")[:512] or None,
    ))
    audit(db, user.id, "session.created")
    await db.commit()
    return user_view(user)

@router.post("/auth/logout")
async def logout(request: Request, response: Response, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    session = await db.get(Session, hash_token(request.cookies.get("gnk_session", "")))
    if session:
        await db.delete(session)
    response.delete_cookie("gnk_session", path="/api", secure=settings.COOKIE_SECURE, httponly=True, samesite="strict")
    await db.commit()
    return {"status": "signed_out"}

@router.get("/me")
async def me(user: User = Depends(get_current_user)):
    return user_view(user)

@router.get("/market")
async def market():
    return {"source": "demonstration", "as_of": None, "currency": "INR", "quotes": [{"symbol": symbol, **q} for symbol, q in QUOTES.items()], "indices": [{"name": "NIFTY 50", "value": "24,834.60", "change": "+0.62%"}, {"name": "SENSEX", "value": "81,765.86", "change": "+0.58%"}, {"name": "BANK NIFTY", "value": "52,108.25", "change": "+0.91%"}]}

@router.get("/instruments")
async def instruments(exchange: Literal["NSE", "BSE"] | None = None):
    items = INSTRUMENTS if exchange is None else tuple(i for i in INSTRUMENTS if i.exchange == exchange)
    return [{
        "exchange": item.exchange,
        "exchange_instrument_id": item.exchange_instrument_id,
        "symbol": item.symbol,
        "name": item.name,
        "asset_class": item.asset_class,
        "currency": item.currency,
        "price_precision": item.price_precision,
        "quantity_precision": item.quantity_precision,
        "price": item.quote,
        "source": "fixed_mock_quote",
    } for item in items]

@router.get("/market/session")
async def market_session():
    now = datetime.now(ZoneInfo("Asia/Kolkata"))
    opening = datetime_time(9, 15)
    closing = datetime_time(15, 30)
    regular_hours = now.weekday() < 5 and opening <= now.time().replace(tzinfo=None) < closing
    return {
        "exchange_timezone": "Asia/Kolkata",
        "local_time": now.isoformat(),
        "regular_session_hours": {"open": "09:15", "close": "15:30"},
        "status": "regular_hours" if regular_hours else "closed",
        "holiday_calendar_loaded": False,
        "enforced_for_paper_orders": False,
    }

async def positions_for(db, user_id):
    positions = (await db.execute(select(Position).where(Position.user_id == user_id, Position.quantity > 0))).scalars().all()
    return [{**row(p, "id exchange symbol quantity average_price"), "ltp": broker.quote(p.symbol), "pnl": (broker.quote(p.symbol) - p.average_price) * p.quantity} for p in positions]

@router.get("/dashboard")
async def dashboard(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    account = await db.get(Account, user.id)
    positions = await positions_for(db, user.id)
    deployments = (await db.execute(select(Deployment).where(Deployment.user_id == user.id))).scalars().all()
    orders = (await db.execute(select(Order).where(Order.user_id == user.id).order_by(Order.created_at.desc()).limit(8))).scalars().all()
    value = sum((p["ltp"] * p["quantity"] for p in positions), Decimal(0))
    return {"mode": "paper", "market_source": "demonstration", "cash": account.cash, "equity": account.cash + value, "invested": value, "realized_pnl": account.realized_pnl, "unrealized_pnl": sum((p["pnl"] for p in positions), Decimal(0)), "killed": account.killed, "broker_connected": account.broker_connected, "kyc_status": account.kyc_status, "subscription": "Paper workspace Â· Free", "active_strategies": sum(d.state == "active" for d in deployments), "positions": positions, "recent_orders": [row(o, "id exchange symbol side quantity price state created_at") for o in orders]}

@router.get("/strategies")
async def strategies(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    deployments = {d.strategy_id: d for d in (await db.execute(select(Deployment).where(Deployment.user_id == user.id))).scalars()}
    return [{**s, "state": deployments[s["id"]].state if s["id"] in deployments else "stopped", "allocation": deployments[s["id"]].allocation if s["id"] in deployments else 100000} for s in STRATEGIES]

class StrategyChange(BaseModel):
    state: Literal["active", "paused", "stopped"]
    allocation: Decimal = Field(ge=1000, le=500000, max_digits=18, decimal_places=2)

@router.patch("/strategies/{strategy_id}")
async def strategy_change(strategy_id: str, body: StrategyChange, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if strategy_id not in {s["id"] for s in STRATEGIES}:
        raise HTTPException(404, "Strategy not found")
    account = await locked_account(db, user)
    if body.state == "active" and (account.killed or not account.broker_connected):
        raise HTTPException(409, "Connect the paper broker and resume trading first")
    deployments = list((await db.execute(select(Deployment).where(Deployment.user_id == user.id))).scalars())
    total = sum((d.allocation for d in deployments if d.strategy_id != strategy_id and d.state == "active"), Decimal(0))
    if body.state == "active" and total + body.allocation > MAX_EXPOSURE:
        raise HTTPException(422, "Combined active strategy allocation exceeds INR 500,000")
    deployment = next((d for d in deployments if d.strategy_id == strategy_id), None)
    if not deployment:
        if body.state == "paused":
            raise HTTPException(409, "A stopped strategy cannot be paused")
        deployment = Deployment(user_id=user.id, strategy_id=strategy_id)
        db.add(deployment)
    if deployment.state == "stopped" and body.state == "paused":
        raise HTTPException(409, "A stopped strategy cannot be paused")
    deployment.state, deployment.allocation = body.state, body.allocation
    audit(db, user.id, "strategy.updated", f"{strategy_id}:{body.state}:{body.allocation}")
    await db.commit()
    return {"state": body.state, "allocation": body.allocation}

class OrderRequest(BaseModel):
    exchange: Literal["NSE", "BSE"] = "NSE"
    symbol: str = Field(max_length=30)
    side: Literal["BUY", "SELL"]
    quantity: int = Field(strict=True, gt=0, le=1000)

async def trading_allowed(db, user, account):
    if account.killed or not account.broker_connected:
        raise HTTPException(409, "Paper trading is paused or broker is disconnected")
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    events = (await db.execute(select(AuditLog).where(AuditLog.user_id == user.id, AuditLog.action == "trade.realized", AuditLog.created_at >= today))).scalars()
    if sum((Decimal(e.detail) for e in events), Decimal(0)) <= -MAX_DAILY_LOSS:
        raise HTTPException(422, "Daily realized loss limit reached")

async def pending_orders(db, user_id):
    return list((await db.execute(select(Order).where(Order.user_id == user_id, Order.state == "pending"))).scalars())

def order_view(o):
    return row(o, "id exchange symbol side quantity price state created_at filled_at")

@router.post("/orders", status_code=201)
async def create_order(body: OrderRequest, idempotency_key: str = Header(min_length=8, max_length=100), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    account = await locked_account(db, user)
    existing = (await db.execute(select(Order).where(Order.user_id == user.id, Order.idempotency_key == idempotency_key))).scalar_one_or_none()
    if existing:
        if (existing.exchange, existing.symbol, existing.side, existing.quantity) != (body.exchange, body.symbol, body.side, body.quantity):
            raise HTTPException(409, "Idempotency key was used for a different order")
        return order_view(existing)
    await trading_allowed(db, user, account)
    if (body.exchange, body.symbol) not in INSTRUMENTS_BY_KEY:
        raise HTTPException(422, "Choose a supported NSE or BSE simulation instrument")
    price = broker.quote(body.symbol)
    pending = await pending_orders(db, user.id)
    positions = await positions_for(db, user.id)
    reserved = sum((o.price * o.quantity for o in pending if o.side == "BUY"), Decimal(0))
    notional = price * body.quantity
    if body.side == "BUY":
        exposure = sum((p["ltp"] * p["quantity"] for p in positions), Decimal(0))
        if notional + reserved > account.cash or exposure + reserved + notional > MAX_EXPOSURE:
            raise HTTPException(422, "Insufficient unreserved capital or INR 500,000 exposure limit exceeded")
    else:
        held = next((p["quantity"] for p in positions if p["exchange"] == body.exchange and p["symbol"] == body.symbol), 0)
        reserved_qty = sum(o.quantity for o in pending if o.exchange == body.exchange and o.symbol == body.symbol and o.side == "SELL")
        if body.quantity + reserved_qty > held:
            raise HTTPException(422, "Insufficient unreserved holdings; short selling is disabled")
    order = Order(user_id=user.id, idempotency_key=idempotency_key, exchange=body.exchange, symbol=body.symbol, side=body.side, quantity=body.quantity, price=price)
    db.add(order)
    audit(db, user.id, "order.submitted", f"{body.side} {body.quantity} {body.exchange}:{body.symbol}")
    await db.commit()
    return order_view(order)

@router.post("/orders/{order_id}/fill")
async def fill_order(order_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    account = await locked_account(db, user)
    order = (await db.execute(select(Order).where(Order.id == order_id, Order.user_id == user.id))).scalar_one_or_none()
    if not order:
        raise HTTPException(404, "Order not found")
    if order.state == "filled":
        return order_view(order)
    if order.state != "pending":
        raise HTTPException(409, "Only pending orders can fill")
    await trading_allowed(db, user, account)
    position = (await db.execute(select(Position).where(Position.user_id == user.id, Position.exchange == order.exchange, Position.symbol == order.symbol))).scalar_one_or_none()
    if not position:
        position = Position(user_id=user.id, exchange=order.exchange, symbol=order.symbol, quantity=0, average_price=Decimal(0))
        db.add(position)
    amount = order.price * order.quantity
    if order.side == "BUY":
        if amount > account.cash:
            raise HTTPException(422, "Insufficient cash")
        position.average_price = ((position.average_price * position.quantity + amount) / (position.quantity + order.quantity)).quantize(Decimal("0.01"))
        position.quantity += order.quantity
        account.cash -= amount
    else:
        if order.quantity > position.quantity:
            raise HTTPException(422, "Insufficient holdings")
        realized = (order.price - position.average_price) * order.quantity
        position.quantity -= order.quantity
        account.cash += amount
        account.realized_pnl += realized
        audit(db, user.id, "trade.realized", str(realized))
    order.state, order.filled_at = "filled", datetime.now(timezone.utc)
    audit(db, user.id, "order.filled", str(order.id))
    await db.commit()
    return order_view(order)

@router.post("/orders/{order_id}/cancel")
async def cancel_order(order_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await locked_account(db, user)
    order = (await db.execute(select(Order).where(Order.id == order_id, Order.user_id == user.id))).scalar_one_or_none()
    if not order:
        raise HTTPException(404, "Order not found")
    if order.state == "filled":
        raise HTTPException(409, "Filled orders cannot be cancelled")
    order.state = "cancelled"
    audit(db, user.id, "order.cancelled", str(order.id))
    await db.commit()
    return order_view(order)

@router.get("/orders")
async def orders(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = (await db.execute(select(Order).where(Order.user_id == user.id).order_by(Order.created_at.desc()).limit(250))).scalars()
    return [order_view(o) for o in result]

@router.get("/positions")
async def positions(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await positions_for(db, user.id)

class Switch(BaseModel):
    enabled: bool

class BrokerConnect(BaseModel):
    provider: Literal["mock"]


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


async def _mock_connection(db: AsyncSession, user_id: uuid.UUID) -> BrokerConnection | None:
    return (await db.execute(select(BrokerConnection).where(
        BrokerConnection.user_id == user_id, BrokerConnection.provider == "mock"
    ))).scalar_one_or_none()


async def _connect_mock(db: AsyncSession, user: User, account: Account):
    try:
        expires_at = mock_broker.authorize()
    except BrokerRateLimitError as error:
        raise HTTPException(429, "Mock broker rate limit reached; retry shortly") from error
    connection = await _mock_connection(db, user.id)
    if connection is None:
        connection = BrokerConnection(user_id=user.id, provider="mock")
        db.add(connection)
    connection.status = "connected"
    connection.credential_expires_at = expires_at
    connection.encrypted_access_token = None
    connection.last_sync_error = None
    account.broker_connected = True
    audit(db, user.id, "broker.connected", "mock:NSE+BSE paper simulation")
    await db.commit()
    return {"provider": "mock", "status": "connected", "mode": "paper", "expires_at": expires_at}


async def _disconnect_mock(db: AsyncSession, user: User, account: Account):
    connection = await _mock_connection(db, user.id)
    if connection and connection.status == "connected":
        try:
            mock_broker.disconnect()
        except BrokerRateLimitError as error:
            raise HTTPException(429, "Mock broker rate limit reached; retry shortly") from error
    if connection:
        connection.status = "disconnected"
        connection.credential_expires_at = None
        connection.encrypted_access_token = None
        connection.last_sync_error = None
    account.broker_connected = False
    audit(db, user.id, "broker.disconnected", "mock")
    await db.commit()
    return {"provider": "mock", "status": "disconnected", "mode": "paper"}


async def _require_mock_connection(db: AsyncSession, user: User) -> tuple[Account, BrokerConnection | None]:
    account = await db.get(Account, user.id)
    connection = await _mock_connection(db, user.id)
    if not account.broker_connected or (connection and connection.status != "connected"):
        raise HTTPException(409, "Connect the mock paper broker first")
    if connection and connection.credential_expires_at and _utc(connection.credential_expires_at) <= datetime.now(timezone.utc):
        connection.status = "expired"
        connection.last_sync_status = "expired"
        connection.last_sync_error = "authorization_expired"
        account.broker_connected = False
        audit(db, user.id, "broker.authorization_expired", "mock")
        await db.commit()
        raise HTTPException(409, "Mock broker authorization expired; reconnect to continue")
    return account, connection


async def _mock_snapshot(db: AsyncSession, user: User):
    account, _ = await _require_mock_connection(db, user)
    positions = (await db.execute(select(Position).where(
        Position.user_id == user.id, Position.quantity > 0
    ).order_by(Position.exchange, Position.symbol))).scalars().all()
    orders = (await db.execute(select(Order).where(
        Order.user_id == user.id
    ).order_by(Order.created_at.desc()).limit(250))).scalars().all()
    normalized_positions = [
        BrokerPosition(
            exchange=position.exchange,
            exchange_instrument_id=INSTRUMENTS_BY_KEY[(position.exchange, position.symbol)].exchange_instrument_id,
            symbol=position.symbol,
            quantity=position.quantity,
            average_price=Decimal(position.average_price),
            last_price=broker.quote(position.symbol),
            unrealized_pnl=(broker.quote(position.symbol) - Decimal(position.average_price)) * position.quantity,
        )
        for position in positions
    ]
    normalized_orders = [
        BrokerOrderStatus(
            order_id=str(order.id),
            exchange=order.exchange,
            exchange_instrument_id=INSTRUMENTS_BY_KEY[(order.exchange, order.symbol)].exchange_instrument_id,
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            status=order.state,
            updated_at=order.filled_at or order.created_at,
        )
        for order in orders
    ]
    summary = await bounded_broker_read(lambda: broker.account_summary(Decimal(account.cash), normalized_positions))
    holdings = await bounded_broker_read(lambda: broker.holdings(normalized_positions))
    current_positions = await bounded_broker_read(lambda: broker.positions(normalized_positions))
    order_status = await bounded_broker_read(lambda: broker.order_status(normalized_orders))

    def position_payload(item: BrokerPosition):
        return {
            "exchange": item.exchange,
            "exchange_instrument_id": item.exchange_instrument_id,
            "symbol": item.symbol,
            "quantity": item.quantity,
            "average_price": item.average_price,
            "last_price": item.last_price,
            "unrealized_pnl": item.unrealized_pnl,
            "currency": "INR",
        }

    return {
        "provider": "mock",
        "mode": "paper",
        "source": "paper_ledger_mirror",
        "account": {"currency": summary.currency, "cash": summary.cash, "equity": summary.equity, "invested": summary.invested},
        "holdings": [position_payload(item) for item in holdings],
        "positions": [position_payload(item) for item in current_positions],
        "orders": [{
            "order_id": item.order_id,
            "exchange": item.exchange,
            "exchange_instrument_id": item.exchange_instrument_id,
            "symbol": item.symbol,
            "side": item.side,
            "quantity": item.quantity,
            "status": item.status,
            "updated_at": item.updated_at,
        } for item in order_status],
    }


@router.post("/broker/connect")
async def connect_broker(
    body: BrokerConnect,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    account = await locked_account(db, user)
    return await _connect_mock(db, user, account)


@router.post("/broker/disconnect")
async def disconnect_broker(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    account = await locked_account(db, user)
    return await _disconnect_mock(db, user, account)


@router.get("/broker/health")
async def broker_health(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _, connection = await _require_mock_connection(db, user)
    expires_at = connection.credential_expires_at if connection else None
    try:
        result = await bounded_broker_read(lambda: broker.health(expires_at, datetime.now(timezone.utc)))
    except BrokerAuthorizationError:
        if connection:
            connection.status = "expired"
            connection.last_sync_status = "expired"
            connection.last_sync_error = "authorization_expired"
        account = await db.get(Account, user.id)
        account.broker_connected = False
        audit(db, user.id, "broker.authorization_expired", "mock")
        await db.commit()
        raise HTTPException(409, "Mock broker authorization expired; reconnect to continue")
    if connection:
        connection.last_health_check_at = result.checked_at
        await db.commit()
    return {"provider": "mock", "status": result.status, "checked_at": result.checked_at, "expires_at": result.expires_at}


@router.get("/broker/account")
async def broker_account(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return (await _mock_snapshot(db, user))["account"]


@router.get("/broker/holdings")
async def broker_holdings(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return (await _mock_snapshot(db, user))["holdings"]


@router.get("/broker/positions")
async def broker_positions(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return (await _mock_snapshot(db, user))["positions"]


@router.get("/broker/orders")
async def broker_orders(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return (await _mock_snapshot(db, user))["orders"]


@router.post("/broker/sync")
async def sync_broker(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    connection = await _mock_connection(db, user.id)
    try:
        _, connection = await _require_mock_connection(db, user)
        health = await bounded_broker_read(
            lambda: broker.health(
                connection.credential_expires_at if connection else None,
                datetime.now(timezone.utc),
            )
        )
        if connection:
            connection.last_health_check_at = health.checked_at
        snapshot = await _mock_snapshot(db, user)
    except HTTPException as error:
        if connection:
            connection.last_synced_at = datetime.now(timezone.utc)
            expired = error.status_code == 409 and "expired" in str(error.detail).lower()
            connection.last_sync_status = "expired" if expired else "error"
            connection.last_sync_error = "authorization_expired" if expired else (
                "rate_limited" if error.status_code == 429 else "sync_failed"
            )
            await db.commit()
        raise
    synced_at = datetime.now(timezone.utc)
    if connection:
        connection.last_synced_at = synced_at
        connection.last_sync_status = "success"
        connection.last_sync_error = None
    audit(db, user.id, "broker.sync.completed", "mock:paper_ledger_mirror")
    await db.commit()
    return snapshot | {"synced_at": synced_at, "sync_status": "success"}


@router.post("/risk/kill-switch")
async def kill_switch(body: Switch, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    account = await locked_account(db, user)
    account.killed = body.enabled
    if body.enabled:
        for order in await pending_orders(db, user.id):
            order.state = "cancelled"
            audit(db, user.id, "order.cancelled", f"{order.id}:kill_switch")
        for deployment in (await db.execute(select(Deployment).where(Deployment.user_id == user.id, Deployment.state == "active"))).scalars():
            deployment.state = "paused"
    audit(db, user.id, "risk.kill_switch", str(body.enabled))
    await db.commit()
    return {"killed": body.enabled, "positions_closed": False}

@router.post("/broker")
async def broker_switch(body: Switch, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    account = await locked_account(db, user)
    result = await (_connect_mock(db, user, account) if body.enabled else _disconnect_mock(db, user, account))
    return {"connected": body.enabled, "broker": "GNK Mock Paper", "mode": "paper", **result}

class Onboarding(BaseModel):
    name: str = Field(min_length=2, max_length=80, pattern=r"\S")
    consent: Literal[True]

@router.post("/onboarding")
async def onboarding(body: Onboarding, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    account = await locked_account(db, user)
    user.name = body.name.strip()
    account.consent_at = datetime.now(timezone.utc)
    account.kyc_status = "profile_submitted"
    audit(db, user.id, "onboarding.profile_submitted", "Paper simulation consent v1; identity verification is not implemented")
    await db.commit()
    return {"status": account.kyc_status, "identity_verified": False}

@router.get("/research")
async def research(user: User = Depends(get_current_user)):
    return [{"id": "risk-basics", "title": "Position sizing before the first trade", "category": "Risk management", "author": "GNK Algo Education", "body": "Compare an order's notional value with virtual capital. Pending buy orders reserve capital. Fixed demonstration prices do not model slippage, fees or market risk.", "disclosure": "Educational demonstration. Not an investment recommendation."}, {"id": "paper-first", "title": "Your paper trading playbook", "category": "Getting started", "author": "GNK Algo Education", "body": "Submit a paper order, then simulate its fill from Orders. Review positions and audit events. Strategy activation records configuration; there are no automated signals in this release.", "disclosure": "Original educational content. No performance claims."}]

@router.get("/subscription")
async def subscription(user: User = Depends(get_current_user)):
    return {"plan": "Paper workspace", "price": 0, "currency": "INR", "status": "active", "payments_enabled": False, "features": ["Virtual INR 10 lakh", "Manual paper orders", "Strategy configuration", "Educational research"]}

@router.post("/subscription/checkout")
async def checkout(user: User = Depends(get_current_user)):
    raise HTTPException(503, "Payments are not configured; no charge has been created")

@router.get("/activity")
async def activity(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = (await db.execute(select(AuditLog).where(AuditLog.user_id == user.id).order_by(AuditLog.created_at.desc()).limit(100))).scalars()
    return [row(e, "id action detail created_at") for e in result]

class Ticket(BaseModel):
    subject: str = Field(min_length=5, max_length=160)
    message: str = Field(min_length=10, max_length=4000)

@router.get("/support")
async def tickets(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return [row(t, "id subject message status created_at") for t in (await db.execute(select(SupportTicket).where(SupportTicket.user_id == user.id).order_by(SupportTicket.created_at.desc()).limit(100))).scalars()]

@router.post("/support", status_code=201)
async def create_ticket(body: Ticket, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    ticket = SupportTicket(user_id=user.id, subject=body.subject, message=body.message)
    db.add(ticket)
    audit(db, user.id, "support.created", body.subject)
    await db.commit()
    return row(ticket, "id subject status")

@router.get("/admin/overview")
async def admin_overview(admin: User = Depends(get_admin), db: AsyncSession = Depends(get_db)):
    users = list((await db.execute(select(User).options(selectinload(User.roles)).order_by(User.created_at.desc()).limit(100))).scalars())
    logs = list((await db.execute(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(100))).scalars())
    audit(db, admin.id, "admin.overview_read")
    await db.commit()
    return {"users": [{**row(u, "id name email is_active email_verified mfa_enabled created_at"), "roles": [r.name for r in u.roles]} for u in users], "audit": [row(e, "id user_id action detail created_at") for e in logs]}
