"""Interactive server-side administrator provisioning and password recovery.

Passwords are read only from the terminal, never from arguments or logs.
"""
import argparse
import asyncio
import getpass

from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy import delete, select, update
from sqlalchemy.orm import selectinload

from app.core.security import get_password_hash, verify_password
from app.db.session import AsyncSessionLocal
from app.models import User, Role, Account, AuditLog, Session, PasswordResetToken, RefreshToken


def normalize_email(value: str) -> str:
    try:
        return str(TypeAdapter(EmailStr).validate_python(value.strip())).lower()
    except ValidationError:
        raise SystemExit("Enter a valid administrator email address") from None


def read_password() -> str:
    password = getpass.getpass("New password (12-128 characters): ")
    confirmation = getpass.getpass("Confirm new password: ")
    if not 12 <= len(password) <= 128:
        raise SystemExit("Password must contain 12-128 characters")
    if password != confirmation:
        raise SystemExit("Passwords do not match; no account changes were made")
    return password


def password_digest(password: str) -> str:
    if not 12 <= len(password) <= 128:
        raise SystemExit("Password must contain 12-128 characters")
    digest = get_password_hash(password)
    if not verify_password(password, digest):
        raise SystemExit("Password verification self-check failed; no account changes were made")
    return digest


async def create_admin(db, email: str, name: str, password: str):
    email = normalize_email(email)
    name = name.strip()
    if not 2 <= len(name) <= 80:
        raise SystemExit("Administrator name must contain 2-80 characters")
    existing = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if existing:
        raise SystemExit("Account already exists; use --reset-password EMAIL for an existing administrator")
    digest = password_digest(password)
    role = (await db.execute(select(Role).where(Role.name == "admin"))).scalar_one_or_none()
    if not role:
        role = Role(name="admin")
        db.add(role)
    user = User(email=email, name=name, hashed_password=digest, roles=[role])
    db.add(user)
    await db.flush()
    db.add(Account(user_id=user.id))
    db.add(AuditLog(user_id=user.id, action="admin.provisioned", detail="Interactive server-side bootstrap with password confirmation"))
    await db.commit()
    return user


async def reset_admin_password(db, email: str, password: str):
    email = normalize_email(email)
    user = (await db.execute(select(User).options(selectinload(User.roles)).where(User.email == email).with_for_update())).scalar_one_or_none()
    if not user or not any(role.name in ("admin", "super_admin") for role in user.roles):
        raise SystemExit("Administrator account not found; no account changes were made")
    if not user.is_active:
        raise SystemExit("Administrator account is suspended; password recovery does not reactivate accounts")
    user.hashed_password = password_digest(password)
    await db.execute(delete(Session).where(Session.user_id == user.id))
    await db.execute(update(PasswordResetToken).where(PasswordResetToken.user_id == user.id).values(used=True))
    await db.execute(update(RefreshToken).where(RefreshToken.user_id == user.id).values(revoked=True))
    db.add(AuditLog(user_id=user.id, action="admin.password_reset", detail="Interactive server-side recovery; all sessions and reset links revoked; roles and MFA preserved"))
    await db.commit()
    return user


async def main(argv=None):
    parser = argparse.ArgumentParser(description="Create an administrator or securely reset an existing administrator password")
    parser.add_argument("--reset-password", metavar="EMAIL", help="Reset an existing active administrator; preserve roles and MFA")
    args = parser.parse_args(argv)
    if args.reset_password:
        email = normalize_email(args.reset_password)
        password = read_password()
        async with AsyncSessionLocal() as db:
            await reset_admin_password(db, email, password)
        print(f"Administrator password updated for {email}. All sessions revoked. Sign in again with your authenticator code if MFA is enabled.")
    else:
        email = normalize_email(input("Administrator email: "))
        name = input("Administrator name: ")
        password = read_password()
        async with AsyncSessionLocal() as db:
            await create_admin(db, email, name, password)
        print(f"Administrator created: {email}. Sign in at /admin/login and complete MFA setup.")


if __name__ == "__main__":
    asyncio.run(main())
