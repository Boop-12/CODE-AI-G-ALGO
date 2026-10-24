import secrets
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Literal
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.api.deps import get_admin, get_current_user, locked_account
from app.brokers import QUOTES, STRATEGIES, broker
from app.core.config import settings
from app.core.security import get_password_hash, verify_password, hash_token, decrypt_mfa_secret, verify_totp
from app.core.mailer import action_url, deliver_link
from app.db.session import get_db
from app.models import User, Account, Session, Deployment, Order, Position, AuditLog, SupportTicket, EmailVerificationToken, LoginHistory, SystemSetting

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
    return {"source": "demonstration", "as_of": None, "quotes": [{"symbol": symbol, **q} for symbol, q in QUOTES.items()], "indices": [{"name": "NIFTY 50", "value": "24,834.60", "change": "+0.62%"}, {"name": "SENSEX", "value": "81,765.86", "change": "+0.58%"}, {"name": "BANK NIFTY", "value": "52,108.25", "change": "+0.91%"}]}

async def positions_for(db, user_id):
    positions = (await db.execute(select(Position).where(Position.user_id == user_id, Position.quantity > 0))).scalars().all()
    return [{**row(p, "id symbol quantity average_price"), "ltp": broker.quote(p.symbol), "pnl": (broker.quote(p.symbol) - p.average_price) * p.quantity} for p in positions]

@router.get("/dashboard")
async def dashboard(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    account = await db.get(Account, user.id)
    positions = await positions_for(db, user.id)
    deployments = (await db.execute(select(Deployment).where(Deployment.user_id == user.id))).scalars().all()
    orders = (await db.execute(select(Order).where(Order.user_id == user.id).order_by(Order.created_at.desc()).limit(8))).scalars().all()
    value = sum((p["ltp"] * p["quantity"] for p in positions), Decimal(0))
    return {"mode": "paper", "market_source": "demonstration", "cash": account.cash, "equity": account.cash + value, "invested": value, "realized_pnl": account.realized_pnl, "unrealized_pnl": sum((p["pnl"] for p in positions), Decimal(0)), "killed": account.killed, "broker_connected": account.broker_connected, "kyc_status": account.kyc_status, "subscription": "Paper workspace · Free", "active_strategies": sum(d.state == "active" for d in deployments), "positions": positions, "recent_orders": [row(o, "id symbol side quantity price state created_at") for o in orders]}

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
    return row(o, "id symbol side quantity price state created_at filled_at")

@router.post("/orders", status_code=201)
async def create_order(body: OrderRequest, idempotency_key: str = Header(min_length=8, max_length=100), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    account = await locked_account(db, user)
    existing = (await db.execute(select(Order).where(Order.user_id == user.id, Order.idempotency_key == idempotency_key))).scalar_one_or_none()
    if existing:
        if (existing.symbol, existing.side, existing.quantity) != (body.symbol, body.side, body.quantity):
            raise HTTPException(409, "Idempotency key was used for a different order")
        return order_view(existing)
    await trading_allowed(db, user, account)
    if body.symbol not in QUOTES:
        raise HTTPException(422, "Choose a supported simulation symbol")
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
        held = next((p["quantity"] for p in positions if p["symbol"] == body.symbol), 0)
        reserved_qty = sum(o.quantity for o in pending if o.symbol == body.symbol and o.side == "SELL")
        if body.quantity + reserved_qty > held:
            raise HTTPException(422, "Insufficient unreserved holdings; short selling is disabled")
    order = Order(user_id=user.id, idempotency_key=idempotency_key, symbol=body.symbol, side=body.side, quantity=body.quantity, price=price)
    db.add(order)
    audit(db, user.id, "order.submitted", f"{body.side} {body.quantity} {body.symbol}")
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
    position = (await db.execute(select(Position).where(Position.user_id == user.id, Position.symbol == order.symbol))).scalar_one_or_none()
    if not position:
        position = Position(user_id=user.id, symbol=order.symbol, quantity=0, average_price=Decimal(0))
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
    account.broker_connected = body.enabled
    audit(db, user.id, "broker.connected" if body.enabled else "broker.disconnected", "Mock broker")
    await db.commit()
    return {"connected": body.enabled, "broker": "GNK Paper", "mode": "paper"}

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
