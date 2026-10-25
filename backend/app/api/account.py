import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, EmailStr, Field, TypeAdapter, field_validator
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_admin, get_current_user, get_super_admin
from app.core.config import settings
from app.core.mailer import action_url, deliver_link
from app.core.security import (
    decrypt_mfa_secret,
    encrypt_mfa_secret,
    generate_totp_secret,
    get_password_hash,
    hash_token,
    verify_password,
    verify_totp,
)
from app.db.session import get_db
from app.models import (
    AuditLog,
    EmailVerificationToken,
    LoginHistory,
    Role,
    Session,
    SystemSetting,
    User,
    PasswordResetToken,
)

router = APIRouter()
SUPPORTED_ROLE_NAMES = {"customer", "research_analyst", "support_staff", "admin", "super_admin"}


def audit(db: AsyncSession, user_id: uuid.UUID, action: str, detail: str = "") -> None:
    db.add(AuditLog(user_id=user_id, action=action, detail=detail))


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _user_view(user: User) -> dict:
    return {
        "id": str(user.id),
        "name": user.name,
        "email": user.email,
        "email_verified": user.email_verified,
        "is_active": user.is_active,
        "theme": user.theme,
        "mfa_enabled": user.mfa_enabled,
        "roles": [role.name for role in user.roles],
    }


class ProfileUpdate(BaseModel):
    name: str = Field(min_length=2, max_length=80, pattern=r"\S")


class PreferenceUpdate(BaseModel):
    theme: Literal["light", "dark", "system"]


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=12, max_length=128)


class TokenBody(BaseModel):
    token: str = Field(min_length=32, max_length=256)

class ForgotPasswordBody(BaseModel):
    email: EmailStr


class ResetBody(TokenBody):
    new_password: str = Field(min_length=12, max_length=128)


class MFACode(BaseModel):
    code: str = Field(pattern=r"^\d{6}$")


class RolesUpdate(BaseModel):
    roles: list[str] = Field(max_length=8)


class ActiveUpdate(BaseModel):
    is_active: bool


class SettingsUpdate(BaseModel):
    settings: dict[str, str] = Field(max_length=20)

    @field_validator("settings")
    @classmethod
    def validate_setting_values(cls, values: dict[str, str]) -> dict[str, str]:
        for key, value in values.items():
            if len(value) > 1000:
                raise ValueError(f"{key} exceeds the maximum setting length")
            if key == "support_email" and value:
                TypeAdapter(EmailStr).validate_python(value)
        return values


@router.get("/profile")
async def profile(user: User = Depends(get_current_user)):
    return _user_view(user)


@router.patch("/profile")
async def update_profile(
    body: ProfileUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user.name = body.name.strip()
    audit(db, user.id, "profile.updated")
    await db.commit()
    return _user_view(user)


@router.get("/settings/account")
async def account_settings(user: User = Depends(get_current_user)):
    return {"theme": user.theme, "email": user.email, "email_verified": user.email_verified}


@router.patch("/settings/account")
async def update_account_settings(
    body: PreferenceUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user.theme = body.theme
    audit(db, user.id, "settings.account.updated", f"theme:{body.theme}")
    await db.commit()
    return {"theme": user.theme}


@router.get("/settings/security")
async def security_settings(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    sessions = list((await db.execute(
        select(Session).where(Session.user_id == user.id, Session.expires_at > datetime.now(timezone.utc))
        .order_by(Session.created_at.desc())
    )).scalars())
    history = list((await db.execute(
        select(LoginHistory).where(LoginHistory.user_id == user.id)
        .order_by(LoginHistory.created_at.desc()).limit(20)
    )).scalars())
    current_hash = hash_token(request.cookies.get("gnk_session", ""))
    return {
        "mfa_enabled": user.mfa_enabled,
        "sessions": [{
            "id": session.token_hash,
            "current": session.token_hash == current_hash,
            "created_at": session.created_at,
            "expires_at": session.expires_at,
            "ip_address": session.ip_address,
            "user_agent": session.user_agent,
        } for session in sessions],
        "login_history": [{
            "id": str(entry.id),
            "created_at": entry.created_at,
            "ip_address": entry.ip_address,
            "user_agent": entry.user_agent,
        } for entry in history],
    }


@router.patch("/settings/security/password")
async def change_password(
    body: PasswordChange,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not verify_password(body.current_password, user.hashed_password):
        raise HTTPException(400, "Current password is incorrect")
    if body.current_password == body.new_password:
        raise HTTPException(422, "Choose a password different from the current password")
    user.hashed_password = get_password_hash(body.new_password)
    sessions = list((await db.execute(select(Session).where(Session.user_id == user.id))).scalars())
    for session in sessions:
        await db.delete(session)
    audit(db, user.id, "password.changed", "All sessions revoked")
    await db.commit()
    return {"status": "password_changed", "sessions_revoked": len(sessions)}


@router.delete("/settings/security/sessions/{session_id}")
async def revoke_session(
    session_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await db.get(Session, session_id)
    if not session or session.user_id != user.id:
        raise HTTPException(404, "Session not found")
    if session_id == hash_token(request.cookies.get("gnk_session", "")):
        raise HTTPException(409, "Use sign out to end the current session")
    await db.delete(session)
    audit(db, user.id, "session.revoked", session_id[:12])
    await db.commit()
    return {"status": "session_revoked"}


@router.post("/auth/verify-email")
async def verify_email(body: TokenBody, db: AsyncSession = Depends(get_db)):
    token = (await db.execute(
        select(EmailVerificationToken).where(EmailVerificationToken.token_hash == hash_token(body.token))
    )).scalar_one_or_none()
    if not token or token.used or _as_utc(token.expires_at) <= datetime.now(timezone.utc):
        raise HTTPException(400, "Verification link is invalid or expired")
    user = await db.get(User, token.user_id)
    if not user or not user.is_active:
        raise HTTPException(400, "Verification link is invalid or expired")
    user.email_verified = True
    token.used = True
    audit(db, user.id, "email.verified")
    await db.commit()
    return {"status": "email_verified"}


@router.post("/auth/resend-verification")
async def resend_verification(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if user.email_verified:
        return {"status": "already_verified"}
    token = secrets.token_urlsafe(32)
    db.add(EmailVerificationToken(
        user_id=user.id,
        token_hash=hash_token(token),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
    ))
    url = action_url("verify-email", token)
    delivered = await deliver_link(user.email, "Verify your GnkAlgo Trader email", f"Verify your email: {url}")
    await db.commit()
    result = {"status": "verification_sent" if delivered else ("delivery_unavailable" if settings.SMTP_HOST else "email_delivery_not_configured")}
    if not delivered and settings.ENVIRONMENT != "production":
        result["development_url"] = url
    return result


@router.post("/auth/forgot-password")
async def forgot_password(body: ForgotPasswordBody, db: AsyncSession = Depends(get_db)):
    normalized = str(body.email).lower()
    user = (await db.execute(select(User).where(User.email == normalized, User.is_active.is_(True)))).scalar_one_or_none()
    result = {"status": "If the account exists, a reset link will be sent"}
    if not user:
        return result
    token = secrets.token_urlsafe(32)
    db.add(PasswordResetToken(
        user_id=user.id,
        token=hash_token(token),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
        used=False,
    ))
    url = action_url("reset-password", token)
    delivered = await deliver_link(user.email, "Reset your GnkAlgo Trader password", f"Reset your password: {url}")
    await db.commit()
    if not delivered and settings.ENVIRONMENT != "production":
        result["development_url"] = url
    return result


@router.post("/auth/reset-password")
async def reset_password(body: ResetBody, db: AsyncSession = Depends(get_db)):
    token_hash = hash_token(body.token)
    reset = (await db.execute(select(PasswordResetToken).where(PasswordResetToken.token == token_hash).with_for_update())).scalar_one_or_none()
    if not reset or reset.used or _as_utc(reset.expires_at) <= datetime.now(timezone.utc):
        raise HTTPException(400, "Reset link is invalid or expired")
    user = await db.get(User, reset.user_id)
    if not user or not user.is_active:
        raise HTTPException(400, "Reset link is invalid or expired")
    user.hashed_password = get_password_hash(body.new_password)
    reset.used = True
    # Invalidate every outstanding link so an older reset email cannot be replayed.
    for other in (await db.execute(select(PasswordResetToken).where(
        PasswordResetToken.user_id == user.id, PasswordResetToken.used.is_(False)
    ))).scalars():
        other.used = True
    sessions = list((await db.execute(select(Session).where(Session.user_id == user.id))).scalars())
    for session in sessions:
        await db.delete(session)
    audit(db, user.id, "password.reset", "All sessions revoked")
    await db.commit()
    return {"status": "password_reset"}


@router.post("/auth/mfa/setup")
async def start_mfa_setup(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.mfa_enabled:
        raise HTTPException(409, "Multi-factor authentication is already enabled; verify your current code before disabling it")
    secret = generate_totp_secret()
    user.mfa_secret = encrypt_mfa_secret(secret)
    user.mfa_enabled = False
    await db.commit()
    label = quote(f"GnkAlgo Trader:{user.email}")
    issuer = quote("GnkAlgo Trader")
    return {
        "secret": secret,
        "otpauth_url": f"otpauth://totp/{label}?secret={secret}&issuer={issuer}",
        "mfa_enabled": False,
    }


@router.post("/auth/mfa/verify")
async def confirm_mfa_setup(
    body: MFACode,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not user.mfa_secret or not verify_totp(decrypt_mfa_secret(user.mfa_secret), body.code):
        raise HTTPException(400, "Authenticator code is invalid")
    user.mfa_enabled = True
    # Only this session proved possession of the authenticator during enrollment.
    # Password-only sessions must not gain admin access when another device enrolls.
    current_hash = hash_token(request.cookies.get("gnk_session", ""))
    for session in (await db.execute(select(Session).where(
        Session.user_id == user.id, Session.token_hash != current_hash
    ))).scalars():
        await db.delete(session)
    audit(db, user.id, "security.mfa.enabled")
    await db.commit()
    return {"mfa_enabled": True}


@router.post("/auth/mfa/disable")
async def disable_mfa(
    body: MFACode,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not user.mfa_enabled or not user.mfa_secret or not verify_totp(decrypt_mfa_secret(user.mfa_secret), body.code):
        raise HTTPException(400, "Authenticator code is invalid")
    user.mfa_enabled = False
    user.mfa_secret = None
    audit(db, user.id, "security.mfa.disabled")
    await db.commit()
    return {"mfa_enabled": False}


@router.get("/admin/users")
async def admin_users(
    q: str = Query(default="", max_length=120),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    admin: User = Depends(get_admin),
    db: AsyncSession = Depends(get_db),
):
    query = select(User)
    if q.strip():
        needle = f"%{q.strip()}%"
        query = query.where(or_(User.name.ilike(needle), User.email.ilike(needle)))
    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar_one()
    users = list((await db.execute(
        query.order_by(User.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        .options(selectinload(User.roles))
    )).scalars())
    return {"items": [_user_view(user) | {"created_at": user.created_at} for user in users], "page": page, "page_size": page_size, "total": total}


@router.get("/admin/users/{user_id}")
async def admin_user_detail(
    user_id: uuid.UUID,
    admin: User = Depends(get_admin),
    db: AsyncSession = Depends(get_db),
):
    user = (await db.execute(select(User).options(selectinload(User.roles)).where(User.id == user_id))).scalar_one_or_none()
    if not user:
        raise HTTPException(404, "User not found")
    return _user_view(user) | {"created_at": user.created_at}


@router.patch("/admin/users/{user_id}/status")
async def update_user_status(
    user_id: uuid.UUID,
    body: ActiveUpdate,
    admin: User = Depends(get_super_admin),
    db: AsyncSession = Depends(get_db),
):
    if user_id == admin.id:
        raise HTTPException(409, "You cannot suspend your own account")
    user = (await db.execute(select(User).options(selectinload(User.roles)).where(User.id == user_id))).scalar_one_or_none()
    if not user:
        raise HTTPException(404, "User not found")
    if not body.is_active and any(role.name == "super_admin" for role in user.roles):
        count = (await db.execute(
            select(func.count(User.id)).join(User.roles).where(User.is_active.is_(True), Role.name == "super_admin")
        )).scalar_one()
        if count <= 1:
            raise HTTPException(409, "Cannot suspend the last active super administrator")
    user.is_active = body.is_active
    if not body.is_active:
        sessions = list((await db.execute(select(Session).where(Session.user_id == user.id))).scalars())
        for session in sessions:
            await db.delete(session)
    audit(db, admin.id, "admin.user.status_changed", f"{user.id}:{'active' if body.is_active else 'suspended'}")
    await db.commit()
    return {"id": str(user.id), "is_active": user.is_active}


@router.get("/admin/roles")
async def admin_roles(admin: User = Depends(get_admin), db: AsyncSession = Depends(get_db)):
    roles = list((await db.execute(select(Role).options(selectinload(Role.users)).order_by(Role.name))).scalars())
    return [{"id": str(role.id), "name": role.name, "users": len(role.users)} for role in roles]


@router.patch("/admin/users/{user_id}/roles")
async def update_user_roles(
    user_id: uuid.UUID,
    body: RolesUpdate,
    admin: User = Depends(get_super_admin),
    db: AsyncSession = Depends(get_db),
):
    if len(set(body.roles)) != len(body.roles) or not set(body.roles).issubset(SUPPORTED_ROLE_NAMES):
        raise HTTPException(422, "One or more roles are not supported")
    user = (await db.execute(select(User).options(selectinload(User.roles)).where(User.id == user_id))).scalar_one_or_none()
    if not user:
        raise HTTPException(404, "User not found")
    currently_super = any(role.name == "super_admin" for role in user.roles)
    keeps_super = "super_admin" in body.roles
    if currently_super and not keeps_super:
        count = (await db.execute(
            select(func.count(User.id)).join(User.roles).where(User.is_active.is_(True), Role.name == "super_admin")
        )).scalar_one()
        if count <= 1:
            raise HTTPException(409, "Cannot remove the last active super administrator")
    roles = list((await db.execute(select(Role).where(Role.name.in_(body.roles)))).scalars())
    known = {role.name for role in roles}
    for name in body.roles:
        if name not in known:
            role = Role(name=name)
            db.add(role)
            roles.append(role)
    user.roles = roles
    audit(db, admin.id, "admin.user.roles_changed", f"{user.id}:{','.join(sorted(body.roles))}")
    await db.commit()
    return _user_view(user)


@router.get("/admin/audit-logs")
async def admin_audit_logs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    admin: User = Depends(get_admin),
    db: AsyncSession = Depends(get_db),
):
    total = (await db.execute(select(func.count(AuditLog.id)))).scalar_one()
    logs = list((await db.execute(
        select(AuditLog).order_by(AuditLog.created_at.desc())
        .offset((page - 1) * page_size).limit(page_size)
    )).scalars())
    return {
        "items": [{"id": str(log.id), "user_id": str(log.user_id), "action": log.action, "detail": log.detail, "created_at": log.created_at} for log in logs],
        "page": page,
        "page_size": page_size,
        "total": total,
    }


@router.get("/admin/settings")
async def admin_settings(admin: User = Depends(get_admin), db: AsyncSession = Depends(get_db)):
    values = list((await db.execute(select(SystemSetting).order_by(SystemSetting.key))).scalars())
    return {item.key: item.value for item in values}


@router.patch("/admin/settings")
async def update_admin_settings(
    body: SettingsUpdate,
    admin: User = Depends(get_super_admin),
    db: AsyncSession = Depends(get_db),
):
    allowed = {"registration_enabled", "support_email"}
    if not set(body.settings).issubset(allowed):
        raise HTTPException(422, "One or more settings are not supported")
    for key, value in body.settings.items():
        if key == "registration_enabled" and value not in {"true", "false"}:
            raise HTTPException(422, f"{key} must be true or false")
        item = await db.get(SystemSetting, key)
        if item:
            item.value = value
            item.updated_at = datetime.now(timezone.utc)
        else:
            db.add(SystemSetting(key=key, value=value))
    audit(db, admin.id, "admin.settings.updated", ",".join(sorted(body.settings)))
    await db.commit()
    return {item.key: item.value for item in (await db.execute(select(SystemSetting).order_by(SystemSetting.key))).scalars()}


@router.get("/settings/brokers")
async def broker_settings(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.models import Account
    account = await db.get(Account, user.id)
    return {"connections": [{"provider": "paper", "label": "GNK paper broker", "connected": account.broker_connected, "mode": "demo"}]}
