import asyncio
import os
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import httpx

os.environ["DATABASE_URL"] = os.getenv("GNK_TEST_DATABASE_URL", "sqlite+aiosqlite:///./test-platform.db")
os.environ["COOKIE_SECURE"] = "false"
os.environ["ENVIRONMENT"] = "test"
os.environ["ALLOWED_ORIGINS"] = "http://testserver"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.main import app
from app.db.session import engine, Base, AsyncSessionLocal
from app.models import User, Role, Session, AuditLog, Position


@pytest.fixture(autouse=True)
def database():
    async def reset():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
            await connection.run_sync(Base.metadata.create_all)
        await engine.dispose()
    asyncio.run(reset())
    yield
    asyncio.run(engine.dispose())


@pytest.fixture
def client():
    with TestClient(app, headers={"Origin": "http://testserver"}) as c:
        yield c


def register(client, email="trader@example.com"):
    response = client.post("/api/v1/auth/register", json={"name": "Test Trader", "email": email, "password": "A-long-test-password-123"})
    assert response.status_code == 201, response.text
    return response.json()


def submit(client, symbol="RELIANCE", quantity=10, side="BUY", key=None):
    return client.post("/api/v1/orders", json={"symbol": symbol, "quantity": quantity, "side": side}, headers={"Idempotency-Key": key or str(uuid.uuid4())})


def test_authentication_logout_and_revocation(client):
    assert client.get("/api/v1/dashboard").status_code == 401
    register(client)
    cookie = client.cookies.get("gnk_session")
    assert len(cookie) > 40
    assert client.get("/api/v1/me").json()["roles"] == []
    assert client.get("/api/v1/admin/overview").status_code == 403
    assert client.post("/api/v1/auth/logout").status_code == 200
    client.cookies.set("gnk_session", cookie)
    assert client.get("/api/v1/me").status_code == 401
    client.cookies.clear()
    assert client.post("/api/v1/auth/login", json={"email": "trader@example.com", "password": "incorrect"}).status_code == 401
    assert client.post("/api/v1/auth/login", json={"email": "trader@example.com", "password": "A-long-test-password-123"}).status_code == 200


def test_password_and_session_are_hashed(client):
    register(client)
    async def inspect():
        async with AsyncSessionLocal() as db:
            user = (await db.execute(select(User))).scalar_one()
            session = (await db.execute(select(Session))).scalar_one()
            assert user.hashed_password.startswith("pbkdf2_sha256$")
            assert client.cookies.get("gnk_session") != session.token_hash
    asyncio.run(inspect())


def test_order_pending_fill_idempotency_and_sell(client):
    register(client)
    key = str(uuid.uuid4())
    response = submit(client, key=key)
    assert response.status_code == 201, response.text
    order = response.json()
    assert order["state"] == "pending"
    assert client.get("/api/v1/positions").json() == []
    assert submit(client, key=key).json()["id"] == order["id"]
    assert submit(client, quantity=11, key=key).status_code == 409
    for _ in range(2):
        assert client.post(f'/api/v1/orders/{order["id"]}/fill').json()["state"] == "filled"
    assert client.get("/api/v1/positions").json()[0]["quantity"] == 10
    assert Decimal(client.get("/api/v1/dashboard").json()["cash"]) == Decimal("970476.00")
    assert client.post(f'/api/v1/orders/{order["id"]}/cancel').status_code == 409
    sell = submit(client, quantity=4, side="SELL").json()
    assert client.post(f'/api/v1/orders/{sell["id"]}/fill').status_code == 200
    assert client.get("/api/v1/positions").json()[0]["quantity"] == 6
    assert Decimal(client.get("/api/v1/dashboard").json()["equity"]) == Decimal("1000000")


def test_exposure_and_pending_buy_reservations(client):
    register(client)
    assert submit(client, quantity=100).status_code == 201
    assert submit(client, quantity=100).status_code == 422
    assert submit(client, quantity=1001).status_code == 422
    assert submit(client, quantity=0).status_code == 422
    assert submit(client, quantity=1.5).status_code == 422
    assert submit(client, symbol="UNKNOWN").status_code == 422
    assert submit(client, side="SELL").status_code == 422


def test_sell_reservations_and_cancel_release(client):
    register(client)
    buy = submit(client).json()
    client.post(f'/api/v1/orders/{buy["id"]}/fill')
    sell = submit(client, quantity=8, side="SELL").json()
    assert submit(client, quantity=3, side="SELL").status_code == 422
    assert client.post(f'/api/v1/orders/{sell["id"]}/cancel').status_code == 200
    assert submit(client, quantity=10, side="SELL").status_code == 201


def test_tenant_isolation(client):
    register(client)
    order = submit(client).json()
    with TestClient(app, headers={"Origin": "http://testserver"}) as other:
        register(other, "other@example.com")
        assert other.get("/api/v1/orders").json() == []
        assert other.post(f'/api/v1/orders/{order["id"]}/fill').status_code == 404
        assert other.post(f'/api/v1/orders/{order["id"]}/cancel').status_code == 404


def test_kill_switch_cancels_orders_pauses_strategies(client):
    register(client)
    assert client.patch("/api/v1/strategies/momentum", json={"state": "active", "allocation": 100000}).status_code == 200
    order = submit(client).json()
    assert client.post("/api/v1/risk/kill-switch", json={"enabled": True}).status_code == 200
    assert client.get("/api/v1/orders").json()[0]["state"] == "cancelled"
    assert client.get("/api/v1/strategies").json()[0]["state"] == "paused"
    assert submit(client).status_code == 409
    assert client.post(f'/api/v1/orders/{order["id"]}/fill').status_code == 409
    assert client.post("/api/v1/risk/kill-switch", json={"enabled": False}).status_code == 200
    assert submit(client).status_code == 201


def test_disconnected_broker_blocks_execution(client):
    register(client)
    order = submit(client).json()
    client.post("/api/v1/broker", json={"enabled": False})
    assert submit(client).status_code == 409
    assert client.post(f'/api/v1/orders/{order["id"]}/fill').status_code == 409


def test_csrf_origin_and_validation(client):
    register(client)
    assert client.post("/api/v1/broker", json={"enabled": False}, headers={"Origin": "https://attacker.example"}).status_code == 403
    del client.headers["Origin"]
    assert client.post("/api/v1/broker", json={"enabled": False}).status_code == 403


def test_strategy_limits_and_transitions(client):
    register(client)
    assert client.patch("/api/v1/strategies/momentum", json={"state": "paused", "allocation": 100000}).status_code == 409
    assert client.patch("/api/v1/strategies/momentum", json={"state": "active", "allocation": 400000}).status_code == 200
    assert client.patch("/api/v1/strategies/balanced", json={"state": "active", "allocation": 200000}).status_code == 422
    assert client.patch("/api/v1/strategies/momentum", json={"state": "active", "allocation": -1}).status_code == 422


def test_expired_session(client):
    register(client)
    async def expire():
        async with AsyncSessionLocal() as db:
            session = (await db.execute(select(Session))).scalar_one()
            session.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            await db.commit()
    asyncio.run(expire())
    assert client.get("/api/v1/dashboard").status_code == 401


def test_daily_loss_limit(client):
    user = register(client)
    async def loss():
        async with AsyncSessionLocal() as db:
            db.add(AuditLog(user_id=uuid.UUID(user["id"]), action="trade.realized", detail="-10000"))
            await db.commit()
    asyncio.run(loss())
    assert submit(client).status_code == 422


def test_support_onboarding_and_payments(client):
    register(client)
    assert client.post("/api/v1/onboarding", json={"name": "Trader", "consent": False}).status_code == 422
    assert client.post("/api/v1/onboarding", json={"name": "Trader", "consent": True}).json()["identity_verified"] is False
    assert client.post("/api/v1/support", json={"subject": "Paper order help", "message": "Please explain the paper fill process."}).status_code == 201
    assert len(client.get("/api/v1/support").json()) == 1
    assert client.get("/api/v1/subscription").json()["payments_enabled"] is False
    assert client.post("/api/v1/subscription/checkout").status_code == 503


def test_admin_authorization(client):
    user = register(client)
    assert client.get("/api/v1/admin/overview").status_code == 403
    async def promote():
        async with AsyncSessionLocal() as db:
            from sqlalchemy.orm import selectinload
            u = (await db.execute(select(User).options(selectinload(User.roles)).where(User.id == uuid.UUID(user["id"])))).scalar_one()
            u.roles.append(Role(name="admin"))
            await db.commit()
    asyncio.run(promote())
    result = client.get("/api/v1/admin/overview")
    assert result.status_code == 200
    assert result.json()["users"][0]["email"] == user["email"]


@pytest.mark.skipif(not os.environ["DATABASE_URL"].startswith("postgresql"), reason="Requires PostgreSQL row locks")
def test_concurrent_submissions_cannot_overreserve(client):
    register(client)
    token = client.cookies.get("gnk_session")
    async def race():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver", headers={"Origin": "http://testserver", "Cookie": f"gnk_session={token}"}) as c:
            async def send():
                return await c.post("/api/v1/orders", json={"symbol": "RELIANCE", "side": "BUY", "quantity": 100}, headers={"Idempotency-Key": str(uuid.uuid4())})
            responses = await asyncio.gather(send(), send())
            assert sorted(r.status_code for r in responses) == [201, 422]
    asyncio.run(race())


@pytest.mark.skipif(not os.environ["DATABASE_URL"].startswith("postgresql"), reason="Requires PostgreSQL row locks")
def test_concurrent_fills_do_not_duplicate_position(client):
    register(client)
    order = submit(client).json()
    token = client.cookies.get("gnk_session")
    async def race():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver", headers={"Origin": "http://testserver", "Cookie": f"gnk_session={token}"}) as c:
            responses = await asyncio.gather(*[c.post(f'/api/v1/orders/{order["id"]}/fill') for _ in range(2)])
            assert [r.status_code for r in responses] == [200, 200]
    asyncio.run(race())
    assert client.get("/api/v1/positions").json()[0]["quantity"] == 10
