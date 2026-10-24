"""Explicit local administrator provisioning; never runs on web registration."""
import asyncio
import getpass
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.core.security import get_password_hash
from app.db.session import AsyncSessionLocal
from app.models import User, Role, Account, AuditLog

async def main():
    email = input("Administrator email: ").strip().lower()
    name = input("Administrator name: ").strip()
    password = getpass.getpass("Password (12+ characters): ")
    if "@" not in email or not name or len(password) < 12:
        raise SystemExit("Valid email, name and a 12+ character password required")
    async with AsyncSessionLocal() as db:
        user = (await db.execute(select(User).options(selectinload(User.roles)).where(User.email == email))).scalar_one_or_none()
        if user:
            raise SystemExit("Account already exists; this command does not change existing roles or passwords")
        role = (await db.execute(select(Role).where(Role.name == "admin"))).scalar_one_or_none()
        if not role:
            role = Role(name="admin")
            db.add(role)
        user = User(email=email, name=name, hashed_password=get_password_hash(password), roles=[role])
        db.add(user)
        await db.flush()
        db.add(Account(user_id=user.id))
        db.add(AuditLog(user_id=user.id, action="admin.provisioned", detail="Interactive server-side bootstrap"))
        await db.commit()
    print("Administrator created. Sign in through the website.")

if __name__ == "__main__":
    asyncio.run(main())
