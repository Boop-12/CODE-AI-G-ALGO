import asyncio
import base64
import hashlib
import hmac
import os
import struct
import time
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from urllib.parse import urlparse, parse_qs
from unittest.mock import AsyncMock
import httpx
from cryptography.fernet import Fernet

os.environ["DATABASE_URL"] = os.getenv("GNK_TEST_DATABASE_URL", "sqlite+aiosqlite:///./test-platform.db")
os.environ["COOKIE_SECURE"] = "false"
os.environ["ENVIRONMENT"] = "test"
os.environ["ALLOWED_ORIGINS"] = "http://testserver"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from app.main import app
from app.db.session import engine, Base, AsyncSessionLocal
from app.models import User, Role, Session, AuditLog, Position, Account, BrokerConnection
from app.core.security import hash_token
from app.core.security import decrypt_broker_token, decrypt_sensitive_value, encrypt_sensitive_value
from app.brokers import mock_broker
from app.broker_providers import PROVIDERS, ProviderSnapshot, ProviderTokens
from app.core.config import settings


@pytest.fixture(autouse=True)
def database():
    async def reset():
        async with engine.begin() as connection:
            await connection.execute(text("DROP TABLE IF EXISTS users"))
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


def totp_code(secret):
    key = base64.b32decode(secret + "=" * (-len(secret) % 8))
    digest = hmac.new(key, struct.pack(">Q", int(time.time() // 30)), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = (struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF) % 1_000_000
    return f"{code:06d}"


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
            assert user.hashed_password.startswith("$argon2id$")
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
    assert client.get("/api/v1/admin/overview").status_code == 403
    secret = client.post("/api/v1/auth/mfa/setup", json={}).json()["secret"]
    assert client.post("/api/v1/auth/mfa/verify", json={"code": totp_code(secret)}).status_code == 200
    result = client.get("/api/v1/admin/overview")
    assert result.status_code == 200
    assert result.json()["users"][0]["email"] == user["email"]
    assert client.get("/api/v1/admin/users").json()["total"] == 1
    assert client.get("/api/v1/admin/roles").status_code == 200
    assert client.get("/api/v1/admin/audit-logs").status_code == 200
    assert client.patch("/api/v1/admin/settings", json={"settings": {"registration_enabled": "false"}}).status_code == 403


def test_super_admin_can_manage_roles_and_suspend_accounts(client):
    admin = register(client, "super-admin@example.com")
    other = TestClient(app, headers={"Origin": "http://testserver"})
    register(other, "managed-user@example.com")

    async def promote():
        async with AsyncSessionLocal() as db:
            from sqlalchemy.orm import selectinload
            user = (await db.execute(select(User).options(selectinload(User.roles)).where(User.id == uuid.UUID(admin["id"])))).scalar_one()
            user.roles.append(Role(name="super_admin"))
            await db.commit()
    asyncio.run(promote())

    secret = client.post("/api/v1/auth/mfa/setup", json={}).json()["secret"]
    assert client.post("/api/v1/auth/mfa/verify", json={"code": totp_code(secret)}).status_code == 200
    listing = client.get("/api/v1/admin/users?q=managed-user&page=1&page_size=1").json()
    assert listing["total"] == 1
    target_id = listing["items"][0]["id"]
    role_result = client.patch(f"/api/v1/admin/users/{target_id}/roles", json={"roles": ["admin"]})
    assert role_result.status_code == 200 and role_result.json()["roles"] == ["admin"]
    suspended = client.patch(f"/api/v1/admin/users/{target_id}/status", json={"is_active": False})
    assert suspended.status_code == 200 and suspended.json()["is_active"] is False
    assert other.get("/api/v1/me").status_code == 401
    other.close()


def test_super_admin_can_assign_support_and_research_roles(client):
    admin = register(client, "ops-admin@example.com")
    other = TestClient(app, headers={"Origin": "http://testserver"})
    register(other, "analyst-target@example.com")

    async def promote():
        async with AsyncSessionLocal() as db:
            from sqlalchemy.orm import selectinload
            user = (await db.execute(select(User).options(selectinload(User.roles)).where(User.id == uuid.UUID(admin["id"])))).scalar_one()
            user.roles.append(Role(name="super_admin"))
            await db.commit()
    asyncio.run(promote())

    secret = client.post("/api/v1/auth/mfa/setup", json={}).json()["secret"]
    assert client.post("/api/v1/auth/mfa/verify", json={"code": totp_code(secret)}).status_code == 200
    listing = client.get("/api/v1/admin/users?q=analyst-target&page=1&page_size=1").json()
    target_id = listing["items"][0]["id"]
    response = client.patch(f"/api/v1/admin/users/{target_id}/roles", json={"roles": ["research_analyst", "support_staff"]})
    assert response.status_code == 200
    assert set(response.json()["roles"]) == {"research_analyst", "support_staff"}
    other.close()


def test_email_verification_profile_settings_and_password_reset(client):
    registered = client.post("/api/v1/auth/register", json={
        "name": "Test Trader",
        "email": "verified@example.com",
        "password": "A-long-test-password-123",
    })
    assert registered.status_code == 201
    verify_url = registered.json()["development_verification_url"]
    verify_token = parse_qs(urlparse(verify_url).fragment)["token"][0]
    assert client.get("/api/v1/profile").json()["email_verified"] is False
    assert client.post("/api/v1/auth/verify-email", json={"token": verify_token}).json()["status"] == "email_verified"
    assert client.get("/api/v1/profile").json()["email_verified"] is True
    assert client.post("/api/v1/auth/verify-email", json={"token": verify_token}).status_code == 400

    profile = client.patch("/api/v1/profile", json={"name": "Updated Trader"})
    assert profile.status_code == 200 and profile.json()["name"] == "Updated Trader"
    assert client.patch("/api/v1/settings/account", json={"theme": "dark"}).json()["theme"] == "dark"
    assert client.get("/api/v1/settings/account").json()["theme"] == "dark"
    security = client.get("/api/v1/settings/security").json()
    assert len(security["sessions"]) == 1 and security["sessions"][0]["current"] is True

    reset = client.post("/api/v1/auth/forgot-password", json={"email": "verified@example.com"})
    reset_url = reset.json()["development_url"]
    reset_token = parse_qs(urlparse(reset_url).fragment)["token"][0]
    async def stored_hash():
        from app.models import PasswordResetToken
        async with AsyncSessionLocal() as db:
            record = (await db.execute(select(PasswordResetToken))).scalar_one()
            assert record.token == hash_token(reset_token)
    asyncio.run(stored_hash())
    assert client.post("/api/v1/auth/reset-password", json={"token": reset_token, "new_password": "A-new-test-password-456"}).status_code == 200
    assert client.get("/api/v1/me").status_code == 401
    assert client.post("/api/v1/auth/reset-password", json={"token": reset_token, "new_password": "A-new-test-password-456"}).status_code == 400
    assert client.post("/api/v1/auth/login", json={"email": "verified@example.com", "password": "A-new-test-password-456"}).status_code == 200


def test_admin_mfa_login_code_is_required(client):
    user = register(client, "mfa-admin@example.com")
    async def promote():
        async with AsyncSessionLocal() as db:
            from sqlalchemy.orm import selectinload
            account_user = (await db.execute(select(User).options(selectinload(User.roles)).where(User.id == uuid.UUID(user["id"])))).scalar_one()
            account_user.roles.append(Role(name="admin"))
            await db.commit()
    asyncio.run(promote())
    secret = client.post("/api/v1/auth/mfa/setup", json={}).json()["secret"]
    assert client.post("/api/v1/auth/mfa/verify", json={"code": totp_code(secret)}).status_code == 200
    client.post("/api/v1/auth/logout")
    credentials = {"email": "mfa-admin@example.com", "password": "A-long-test-password-123"}
    assert client.post("/api/v1/auth/login", json=credentials).status_code == 401
    assert client.post("/api/v1/auth/login", json={**credentials, "mfa_code": "000000"}).status_code == 401
    assert client.post("/api/v1/auth/login", json={**credentials, "mfa_code": totp_code(secret)}).status_code == 200
    assert client.post("/api/v1/auth/mfa/setup", json={}).status_code == 409
    assert client.post("/api/v1/auth/mfa/disable", json={"code": "000000"}).status_code == 400
    assert client.post("/api/v1/auth/mfa/disable", json={"code": totp_code(secret)}).status_code == 200
    assert client.get("/api/v1/admin/overview").status_code == 403


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


def test_legacy_password_upgrade_only_after_successful_login(client):
    user = register(client, "legacy@example.com")
    salt = "0123456789abcdef0123456789abcdef"
    password = "A-long-test-password-123"
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 600_000).hex()
    legacy = f"pbkdf2_sha256$600000${salt}${digest}"

    async def set_legacy():
        async with AsyncSessionLocal() as db:
            account = await db.get(User, uuid.UUID(user["id"]))
            account.hashed_password = legacy
            await db.commit()
    asyncio.run(set_legacy())
    client.post("/api/v1/auth/logout")
    assert client.post("/api/v1/auth/login", json={"email": "legacy@example.com", "password": "wrong-password"}).status_code == 401

    async def password_hash():
        async with AsyncSessionLocal() as db:
            return (await db.get(User, uuid.UUID(user["id"]))).hashed_password
    assert asyncio.run(password_hash()) == legacy
    assert client.post("/api/v1/auth/login", json={"email": "legacy@example.com", "password": password}).status_code == 200
    assert asyncio.run(password_hash()).startswith("$argon2id$")


def test_validation_never_echoes_secrets(client):
    password = "short-secret"
    result = client.post("/api/v1/auth/register", json={"name": "Trader", "email": "invalid", "password": password})
    assert result.status_code == 422 and password not in result.text
    token = "private-token-too-short"
    result = client.post("/api/v1/auth/reset-password", json={"token": token, "new_password": password})
    assert result.status_code == 422 and token not in result.text and password not in result.text


def test_reset_invalidates_all_outstanding_links(client):
    register(client, "multiple-reset@example.com")
    tokens = []
    for _ in range(2):
        response = client.post("/api/v1/auth/forgot-password", json={"email": "multiple-reset@example.com"})
        tokens.append(parse_qs(urlparse(response.json()["development_url"]).fragment)["token"][0])
    assert client.post("/api/v1/auth/reset-password", json={"token": tokens[1], "new_password": "Replacement-password-123!"}).status_code == 200
    assert client.post("/api/v1/auth/reset-password", json={"token": tokens[0], "new_password": "Attacker-password-123!"}).status_code == 400


def test_mfa_enrollment_revokes_other_password_only_sessions(client):
    user = register(client, "enrollment-admin@example.com")
    other = TestClient(app, headers={"Origin": "http://testserver"})
    assert other.post("/api/v1/auth/login", json={"email": user["email"], "password": "A-long-test-password-123"}).status_code == 200

    async def promote():
        from sqlalchemy.orm import selectinload
        async with AsyncSessionLocal() as db:
            account = (await db.execute(select(User).options(selectinload(User.roles)).where(User.id == uuid.UUID(user["id"])))).scalar_one()
            account.roles.append(Role(name="admin"))
            await db.commit()
    asyncio.run(promote())
    assert other.get("/api/v1/admin/overview").status_code == 403
    secret = client.post("/api/v1/auth/mfa/setup", json={}).json()["secret"]
    assert client.post("/api/v1/auth/mfa/verify", json={"code": totp_code(secret)}).status_code == 200
    assert client.get("/api/v1/admin/overview").status_code == 200
    assert other.get("/api/v1/me").status_code == 401
    other.close()



def test_single_database_legacy_import_is_additive_idempotent_and_unprivileged(client):
    from app.import_legacy_accounts import import_accounts
    from app.models import Account, LegacyAccountImport
    from app.core.security import get_password_hash, verify_password
    from sqlalchemy import text, func
    existing = register(client, "existing-target@example.com")
    password = "Legacy-password-123!"
    stored_hash = get_password_hash(password)

    async def run():
        async with AsyncSessionLocal() as db:
            await db.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT, email TEXT, password_hash TEXT, is_active BOOLEAN, created_at TEXT)"))
            await db.execute(text("INSERT INTO users VALUES (42, 'Legacy User', 'legacy-user@example.com', :hash, true, '2025-01-01')"), {"hash": stored_hash})
            await db.commit()
            preview = await import_accounts(db)
            assert preview["eligible"] == 1 and preview["imported"] == 0
            assert (await db.execute(select(func.count(User.id)))).scalar_one() == 1
            await db.rollback()
            result = await import_accounts(db, apply=True)
            await db.commit()
            assert result["imported"] == 1
            again = await import_accounts(db, apply=True)
            await db.commit()
            assert again["already_imported"] == 1 and again["imported"] == 0
            legacy = (await db.execute(select(User).where(User.email == "legacy-user@example.com"))).scalar_one()
            assert verify_password(password, legacy.hashed_password)
            assert legacy.email_verified is False and legacy.mfa_enabled is False
            assert legacy.created_at.year == 2025
            assert await db.get(Account, legacy.id) is not None
            assert (await db.execute(select(LegacyAccountImport))).scalar_one().user_id == legacy.id
            assert (await db.execute(text("SELECT password_hash FROM users WHERE id=42"))).scalar_one() == stored_hash
            assert await db.get(User, uuid.UUID(existing["id"])) is not None
    asyncio.run(run())
    client.post("/api/v1/auth/logout")
    result = client.post("/api/v1/auth/login", json={"email": "legacy-user@example.com", "password": password})
    assert result.status_code == 200 and result.json()["roles"] == []
    assert client.get("/api/v1/admin/users").status_code == 403


def test_legacy_import_collision_refuses_all_writes(client):
    from app.import_legacy_accounts import ImportConflict, import_accounts
    from app.core.security import get_password_hash
    from sqlalchemy import text, func
    register(client, "collision@example.com")

    async def run():
        async with AsyncSessionLocal() as db:
            await db.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT, email TEXT, password_hash TEXT, is_active BOOLEAN, created_at TEXT)"))
            for identifier, email in [(1, "new-source@example.com"), (2, "COLLISION@example.com")]:
                await db.execute(text("INSERT INTO users VALUES (:id, 'Source', :email, :hash, true, '2025-01-01')"), {"id": identifier, "email": email, "hash": get_password_hash("Legacy-password-123!")})
            await db.commit()
            preview = await import_accounts(db)
            assert preview["email_conflicts"] == 1
            with pytest.raises(ImportConflict):
                await import_accounts(db, apply=True)
            await db.rollback()
            assert (await db.execute(select(func.count(User.id)))).scalar_one() == 1
            assert (await db.execute(text("SELECT COUNT(*) FROM users"))).scalar_one() == 2
    asyncio.run(run())



def test_legacy_import_invalid_password_refuses_writes(client):
    from app.import_legacy_accounts import ImportConflict, import_accounts
    from sqlalchemy import text, func

    async def run():
        async with AsyncSessionLocal() as db:
            await db.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT, email TEXT, password_hash TEXT, is_active BOOLEAN, created_at TEXT)"))
            await db.execute(text("INSERT INTO users VALUES (1, 'Source', 'invalid-hash@example.com', 'plaintext-is-forbidden', true, '2025-01-01')"))
            await db.commit()
            preview = await import_accounts(db)
            assert preview["invalid_records"] == 1
            with pytest.raises(ImportConflict):
                await import_accounts(db, apply=True)
            await db.rollback()
            assert (await db.execute(select(func.count(User.id)))).scalar_one() == 0
    asyncio.run(run())


def test_admin_bootstrap_confirmed_password_round_trip(client, monkeypatch):
    from app.bootstrap import main
    inputs = iter(["  BOOTSTRAP.ADMIN@EXAMPLE.COM  ", "Bootstrap Admin"])
    passwords = iter(["Confirmed-admin-password-123!", "Confirmed-admin-password-123!"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))
    monkeypatch.setattr("getpass.getpass", lambda _: next(passwords))
    asyncio.run(main([]))
    result = client.post("/api/v1/auth/login", json={"email": "bootstrap.admin@example.com", "password": "Confirmed-admin-password-123!"})
    assert result.status_code == 200, result.text
    assert result.json()["roles"] == ["admin"]
    assert result.json()["mfa_enabled"] is False
    assert client.get("/api/v1/admin/overview").status_code == 403  # Enrollment is still required.


def test_admin_bootstrap_rejects_mismatched_password_without_writes(client, monkeypatch):
    from app.bootstrap import main
    from sqlalchemy import func
    inputs = iter(["bootstrap@example.com", "Bootstrap Admin"])
    passwords = iter(["First-password-123!", "Different-password-123!"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))
    monkeypatch.setattr("getpass.getpass", lambda _: next(passwords))
    with pytest.raises(SystemExit, match="do not match"):
        asyncio.run(main([]))
    async def count_users():
        async with AsyncSessionLocal() as db:
            return (await db.execute(select(func.count(User.id)))).scalar_one()
    assert asyncio.run(count_users()) == 0


def test_admin_password_recovery_revokes_sessions_and_preserves_mfa(client):
    from app.bootstrap import create_admin, reset_admin_password
    from app.models import PasswordResetToken, RefreshToken
    from app.core.security import encrypt_mfa_secret, verify_password
    secret = "JBSWY3DPEHPK3PXP"
    async def prepare():
        async with AsyncSessionLocal() as db:
            admin = await create_admin(db, "recover@example.com", "Recovery Admin", "Original-admin-password-123!")
            admin.mfa_enabled, admin.mfa_secret = True, encrypt_mfa_secret(secret)
            db.add(Session(user_id=admin.id, token_hash=hash_token("old-session"), expires_at=datetime.now(timezone.utc) + timedelta(hours=1)))
            db.add(PasswordResetToken(user_id=admin.id, token=hash_token("old-reset-link"), expires_at=datetime.now(timezone.utc) + timedelta(minutes=30)))
            db.add(RefreshToken(user_id=admin.id, token="legacy-refresh-token", expires_at=datetime.now(timezone.utc) + timedelta(hours=1)))
            await db.commit()
            await reset_admin_password(db, " RECOVER@EXAMPLE.COM ", "Recovered-admin-password-456!")
            assert admin.mfa_enabled and admin.mfa_secret
            assert [r.name for r in admin.roles] == ["admin"]
            assert verify_password("Recovered-admin-password-456!", admin.hashed_password)
            assert not verify_password("Original-admin-password-123!", admin.hashed_password)
            assert list((await db.execute(select(Session).where(Session.user_id == admin.id))).scalars()) == []
            assert (await db.execute(select(PasswordResetToken))).scalar_one().used
            assert (await db.execute(select(RefreshToken))).scalar_one().revoked
    asyncio.run(prepare())
    credentials = {"email": "recover@example.com", "password": "Recovered-admin-password-456!"}
    assert client.post("/api/v1/auth/login", json=credentials).status_code == 401
    assert client.post("/api/v1/auth/login", json={**credentials, "mfa_code": totp_code(secret)}).status_code == 200


def test_admin_password_recovery_cannot_promote_customer_or_reactivate_admin(client):
    from app.bootstrap import create_admin, reset_admin_password
    from app.core.security import verify_password
    register(client, "customer@example.com")
    async def run():
        async with AsyncSessionLocal() as db:
            with pytest.raises(SystemExit, match="not found"):
                await reset_admin_password(db, "customer@example.com", "Replacement-password-123!")
            await db.rollback()
            customer = (await db.execute(select(User).where(User.email == "customer@example.com"))).scalar_one()
            assert verify_password("A-long-test-password-123", customer.hashed_password)
            admin = await create_admin(db, "suspended@example.com", "Suspended Admin", "Original-admin-password-123!")
            admin.is_active = False
            await db.commit()
            with pytest.raises(SystemExit, match="suspended"):
                await reset_admin_password(db, "suspended@example.com", "Replacement-password-123!")
            assert admin.is_active is False
            assert verify_password("Original-admin-password-123!", admin.hashed_password)
    asyncio.run(run())


def test_admin_bootstrap_duplicate_does_not_overwrite_and_password_limits(client):
    from app.bootstrap import create_admin, password_digest
    from app.core.security import verify_password
    for password in ("too-short", "x" * 129):
        with pytest.raises(SystemExit, match="12-128"):
            password_digest(password)
    async def run():
        async with AsyncSessionLocal() as db:
            admin = await create_admin(db, "duplicate@example.com", "Original Admin", "Original-admin-password-123!")
            with pytest.raises(SystemExit, match="already exists"):
                await create_admin(db, "duplicate@example.com", "Replacement Admin", "Replacement-password-123!")
            assert verify_password("Original-admin-password-123!", admin.hashed_password)
            assert admin.name == "Original Admin"
    asyncio.run(run())


def test_mock_broker_connection_sync_is_exchange_aware_and_tenant_scoped(client):
    register(client, "broker-owner@example.com")
    settings = client.get("/api/v1/settings/brokers").json()
    assert {provider["id"] for provider in settings["providers"]} == {"mock", "zerodha", "dhan", "fyers"}
    assert settings["providers"][0]["available"] is True
    assert settings["providers"][0]["capabilities"]["exchanges"] == ["NSE", "BSE"]
    assert settings["providers"][0]["capabilities"]["segments"] == ["EQUITY", "ETF"]
    assert settings["providers"][0]["capabilities"]["order_placement"] is False
    assert all(provider["available"] is False for provider in settings["providers"][1:])
    assert settings["connections"][0]["connected"] is True
    connected = client.post("/api/v1/broker/connect", json={"provider": "mock"})
    assert connected.status_code == 200
    assert "access_token" not in connected.json()
    assert client.get("/api/v1/broker/health").json()["status"] == "connected"

    instruments = client.get("/api/v1/instruments").json()
    nse_reliance = next(item for item in instruments if item["exchange"] == "NSE" and item["symbol"] == "RELIANCE")
    bse_reliance = next(item for item in instruments if item["exchange"] == "BSE" and item["symbol"] == "RELIANCE")
    assert nse_reliance["exchange_instrument_id"] == "RELIANCE"
    assert bse_reliance["exchange_instrument_id"] == "500325"
    assert nse_reliance["currency"] == "INR" and nse_reliance["quantity_precision"] == 0
    assert any(item["asset_class"] == "ETF" for item in instruments)
    session = client.get("/api/v1/market/session").json()
    assert session["exchange_timezone"] == "Asia/Kolkata"
    assert session["holiday_calendar_loaded"] is False
    assert session["enforced_for_paper_orders"] is False

    for exchange in ("NSE", "BSE"):
        order = client.post(
            "/api/v1/orders",
            json={"exchange": exchange, "symbol": "RELIANCE", "side": "BUY", "quantity": 2},
            headers={"Idempotency-Key": f"broker-{exchange.lower()}-order"},
        )
        assert order.status_code == 201, order.text
        assert order.json()["exchange"] == exchange
        assert client.post(f"/api/v1/orders/{order.json()['id']}/fill").status_code == 200

    first_sync = client.post("/api/v1/broker/sync").json()
    second_sync = client.post("/api/v1/broker/sync").json()
    assert first_sync["sync_status"] == second_sync["sync_status"] == "success"
    assert first_sync["source"] == "paper_ledger_mirror"
    assert {(item["exchange"], item["symbol"]) for item in first_sync["positions"]} == {
        ("NSE", "RELIANCE"), ("BSE", "RELIANCE")
    }
    assert len(first_sync["orders"]) == len(second_sync["orders"]) == 2
    assert client.get("/api/v1/broker/account").json()["currency"] == "INR"
    assert len(client.get("/api/v1/broker/holdings").json()) == 2
    assert client.get("/api/v1/settings/brokers").json()["connections"][0]["last_sync_status"] == "success"

    async def inspect_connection():
        async with AsyncSessionLocal() as db:
            connection = (await db.execute(select(BrokerConnection))).scalar_one()
            account = (await db.execute(select(Account))).scalar_one()
            assert connection.status == "connected"
            assert connection.last_sync_status == "success"
            assert connection.encrypted_access_token is None
            assert account.broker_connected is True
    asyncio.run(inspect_connection())

    with TestClient(app, headers={"Origin": "http://testserver"}) as other:
        register(other, "other-broker-owner@example.com")
        assert other.get("/api/v1/broker/positions").json() == []
        assert other.post("/api/v1/broker/sync").json()["orders"] == []

    disconnected = client.post("/api/v1/broker/disconnect")
    assert disconnected.json()["status"] == "disconnected"
    assert client.get("/api/v1/settings/brokers").json()["connections"][0]["connected"] is False
    assert client.post("/api/v1/broker/sync").status_code == 409


def test_mock_broker_expiration_and_bounded_rate_limit_handling(client):
    register(client, "broker-expiry@example.com")
    assert client.post("/api/v1/broker/connect", json={"provider": "mock"}).status_code == 200

    async def expire_connection():
        async with AsyncSessionLocal() as db:
            connection = (await db.execute(select(BrokerConnection))).scalar_one()
            connection.credential_expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
            await db.commit()
    asyncio.run(expire_connection())

    expired = client.post("/api/v1/broker/sync")
    assert expired.status_code == 409
    assert "expired" in expired.json()["detail"].lower()
    settings = client.get("/api/v1/settings/brokers").json()["connections"][0]
    assert settings["status"] == "expired" and settings["connected"] is False
    assert client.get("/api/v1/broker/health").status_code == 409
    assert submit(client).status_code == 409

    assert client.post("/api/v1/broker/connect", json={"provider": "mock"}).status_code == 200
    before = mock_broker.rate_limit_attempts
    mock_broker.rate_limit_failures = 1
    try:
        assert client.get("/api/v1/broker/health").status_code == 200
        assert mock_broker.rate_limit_attempts - before == 2
        before = mock_broker.rate_limit_attempts
        mock_broker.rate_limit_failures = 3
        limited = client.post("/api/v1/broker/sync")
        assert limited.status_code == 429
        assert mock_broker.rate_limit_attempts - before == 3
    finally:
        mock_broker.rate_limit_failures = 0

    async def check_sync_failure():
        async with AsyncSessionLocal() as db:
            connection = (await db.execute(select(BrokerConnection))).scalar_one()
            assert connection.last_sync_status == "error"
            assert connection.last_sync_error == "rate_limited"
    asyncio.run(check_sync_failure())


def test_sensitive_token_encryption_helpers_do_not_store_plaintext():
    token = "mock-provider-token-for-encryption-test"
    encrypted = encrypt_sensitive_value(token)
    assert token not in encrypted
    assert decrypt_sensitive_value(encrypted) == token


def test_live_broker_authorization_sync_tenant_isolation_and_disconnect(client, monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "BROKER_TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode())
    adapter = PROVIDERS["zerodha"]
    monkeypatch.setattr(adapter, "configured", lambda: True)
    monkeypatch.setattr(adapter, "begin_authorization", AsyncMock(return_value=(
        "https://broker.example/authorize", None
    )))
    monkeypatch.setattr(adapter, "complete_authorization", AsyncMock(return_value=ProviderTokens(
        access_token="server-only-access-token",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=8),
        account_id="provider-account-123",
        account_label="Zerodha account",
    )))
    snapshot = ProviderSnapshot(
        provider="zerodha",
        account={"currency": "INR", "available_balance": Decimal("1234.50")},
        holdings=[{"exchange": "NSE", "symbol": "TEST", "quantity": 2}],
        positions=[],
        orders=[],
        fetched_at=datetime.now(timezone.utc),
    )
    monkeypatch.setattr(adapter, "snapshot", AsyncMock(return_value=snapshot))

    register(client, "live-broker-owner@example.com")
    owner_cookie = client.cookies.get("gnk_session")
    started = client.post("/api/v1/broker/zerodha/connect", json={})
    assert started.status_code == 200, started.text
    assert started.json()["authorization_url"] == "https://broker.example/authorize"
    assert "access_token" not in started.text
    state = client.cookies.get("gnk_broker_state_zerodha")
    assert state

    callback = client.get(
        f"/api/v1/broker/callback/zerodha?status=success&request_token=one-time&state={state}",
        follow_redirects=False,
    )
    assert callback.status_code == 303
    assert "connection=connected" in callback.headers["location"]
    replay = client.get(
        f"/api/v1/broker/callback/zerodha?status=success&request_token=one-time&state={state}",
        follow_redirects=False,
    )
    assert replay.status_code == 400

    async def check_stored_token():
        async with AsyncSessionLocal() as db:
            connection = (await db.execute(select(BrokerConnection))).scalar_one()
            assert connection.provider == "zerodha"
            assert connection.provider_account_id == "provider-account-123"
            assert connection.status == "connected"
            assert connection.encrypted_access_token != "server-only-access-token"
            assert decrypt_broker_token(connection.encrypted_access_token) == "server-only-access-token"
    asyncio.run(check_stored_token())

    broker_settings = client.get("/api/v1/settings/brokers")
    assert broker_settings.status_code == 200
    assert {item["id"] for item in broker_settings.json()["providers"]} == {"zerodha", "dhan", "fyers"}
    assert all(item["capabilities"]["order_placement"] is False for item in broker_settings.json()["providers"])
    assert "server-only-access-token" not in broker_settings.text

    sync1 = client.post("/api/v1/broker/zerodha/sync")
    sync2 = client.post("/api/v1/broker/zerodha/sync")
    assert sync1.status_code == sync2.status_code == 200
    assert sync1.json()["account"]["available_balance"] == "1234.50"
    assert sync1.json()["sync_status"] == sync2.json()["sync_status"] == "success"
    assert "server-only-access-token" not in sync1.text

    register(client, "other-live-broker-user@example.com")
    assert client.post("/api/v1/broker/zerodha/sync").status_code == 409
    client.cookies.set("gnk_session", owner_cookie)
    disconnected = client.post("/api/v1/broker/zerodha/disconnect")
    assert disconnected.status_code == 200
    assert disconnected.json()["local_token_deleted"] is True
    assert disconnected.json()["provider_session_revoked"] is False

    async def check_disconnected():
        async with AsyncSessionLocal() as db:
            connection = (await db.execute(select(BrokerConnection))).scalar_one()
            assert connection.status == "disconnected"
            assert connection.encrypted_access_token is None
    asyncio.run(check_disconnected())


def test_live_broker_authorization_is_production_only(client):
    register(client, "production-gated-broker@example.com")
    response = client.post("/api/v1/broker/zerodha/connect", json={})
    assert response.status_code == 404


def test_real_provider_auth_flows_use_mocked_http_and_provider_expiry(monkeypatch):
    import hashlib
    import app.broker_providers as broker_providers
    from zoneinfo import ZoneInfo

    monkeypatch.setattr(settings, "ZERODHA_API_KEY", "test-zerodha-app")
    monkeypatch.setattr(settings, "ZERODHA_API_SECRET", "test-zerodha-secret")
    zerodha_exchange = AsyncMock(return_value={
        "status": "success",
        "data": {"access_token": "zerodha-token", "user_id": "Z123"},
    })
    monkeypatch.setattr(broker_providers, "_request_json", zerodha_exchange)
    now_ist = datetime.now(ZoneInfo("Asia/Kolkata"))
    zerodha_tokens = asyncio.run(PROVIDERS["zerodha"].complete_authorization(
        {"status": "success", "request_token": "one-time-token"}, None
    ))
    expiry_ist = zerodha_tokens.expires_at.astimezone(ZoneInfo("Asia/Kolkata"))
    assert expiry_ist.hour == 6 and expiry_ist.minute == 0
    assert expiry_ist.date() > now_ist.date()
    assert zerodha_exchange.await_args.args[0] == "POST"

    monkeypatch.setattr(settings, "DHAN_PARTNER_ID", "test-partner")
    monkeypatch.setattr(settings, "DHAN_PARTNER_SECRET", "test-partner-secret")
    dhan_exchange = AsyncMock(return_value={
        "accessToken": "dhan-token",
        "expiryTime": "2030-01-02T13:00:00+05:30",
        "dhanClientId": "D123",
    })
    monkeypatch.setattr(broker_providers, "_request_json", dhan_exchange)
    dhan_tokens = asyncio.run(PROVIDERS["dhan"].complete_authorization({"tokenId": "temporary-token"}, "consent"))
    assert dhan_tokens.expires_at == datetime(2030, 1, 2, 7, 30, tzinfo=timezone.utc)

    monkeypatch.setattr(settings, "FYERS_APP_ID", "test-fyers-app")
    monkeypatch.setattr(settings, "FYERS_SECRET_KEY", "test-fyers-secret")
    fyers_exchange = AsyncMock(return_value={
        "s": "ok", "access_token": "fyers-token", "fy_id": "F123",
    })
    monkeypatch.setattr(broker_providers, "_request_json", fyers_exchange)
    fyers_url, _ = asyncio.run(PROVIDERS["fyers"].begin_authorization("csrf-state"))
    assert "csrf-state" in fyers_url
    fyers_tokens = asyncio.run(PROVIDERS["fyers"].complete_authorization({"auth_code": "one-time-code"}, None))
    assert fyers_tokens.expires_at is None
    assert fyers_tokens.account_id == "F123"
    assert fyers_exchange.await_args.kwargs["json"]["appIdHash"] == hashlib.sha256(
        b"test-fyers-app:test-fyers-secret"
    ).hexdigest()


def test_provider_get_rate_limit_retries_are_bounded(monkeypatch):
    import app.broker_providers as broker_providers

    attempts = []

    class Response:
        headers = {"Retry-After": "0"}

        def __init__(self, status_code):
            self.status_code = status_code

        def json(self):
            return {"status": "success", "data": []}

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def request(self, *_args, **_kwargs):
            attempts.append(1)
            return Response(429 if len(attempts) < 3 else 200)

    monkeypatch.setattr(broker_providers.httpx, "AsyncClient", lambda **_: Client())
    monkeypatch.setattr(broker_providers.asyncio, "sleep", AsyncMock())
    response = asyncio.run(broker_providers._request_json("GET", "https://broker.example/read"))
    assert response["status"] == "success"
    assert len(attempts) == 3

    attempts.clear()
    with pytest.raises(broker_providers.BrokerProviderError) as error:
        asyncio.run(broker_providers._request_json("POST", "https://broker.example/auth"))
    assert error.value.rate_limited is True
    assert len(attempts) == 1
