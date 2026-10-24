from datetime import datetime, timezone
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.core.security import hash_token
from app.db.session import get_db
from app.models import User, Session, Account

async def get_current_user(request: Request, db: AsyncSession = Depends(get_db)) -> User:
    session = await db.get(Session, hash_token(request.cookies.get("gnk_session", "")))
    if not session or session.expires_at.replace(tzinfo=timezone.utc) <= datetime.now(timezone.utc):
        raise HTTPException(401, "Please sign in to continue")
    user = (await db.execute(select(User).options(selectinload(User.roles)).where(User.id == session.user_id))).scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(401, "Account unavailable")
    return user

async def get_admin(user: User = Depends(get_current_user)) -> User:
    if not any(r.name in ("admin", "super_admin") for r in user.roles):
        raise HTTPException(403, "Administrator access required")
    if not user.mfa_enabled or not user.mfa_secret:
        raise HTTPException(403, "Set up multi-factor authentication before using administrator tools")
    return user

async def get_super_admin(user: User = Depends(get_admin)) -> User:
    if not any(r.name == "super_admin" for r in user.roles):
        raise HTTPException(403, "Super administrator access required")
    return user

async def locked_account(db: AsyncSession, user: User) -> Account:
    return (await db.execute(select(Account).where(Account.user_id == user.id).with_for_update())).scalar_one()
