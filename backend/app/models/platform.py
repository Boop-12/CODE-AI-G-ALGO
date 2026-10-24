import uuid
from datetime import datetime, timezone
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base


def utcnow():
    return datetime.now(timezone.utc)


class Account(Base):
    __tablename__ = "paper_account"
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("user.id"), primary_key=True)
    cash: Mapped[float] = mapped_column(Numeric(18, 2), default=1000000)
    realized_pnl: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    killed: Mapped[bool] = mapped_column(Boolean, default=False)
    broker_connected: Mapped[bool] = mapped_column(Boolean, default=True)
    kyc_status: Mapped[str] = mapped_column(String(30), default="not_submitted")
    consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Session(Base):
    __tablename__ = "browser_session"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("user.id"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Deployment(Base):
    __tablename__ = "strategy_deployment"
    __table_args__ = (UniqueConstraint("user_id", "strategy_id"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("user.id"), index=True)
    strategy_id: Mapped[str] = mapped_column(String(40))
    state: Mapped[str] = mapped_column(String(20), default="stopped")
    allocation: Mapped[float] = mapped_column(Numeric(18, 2), default=100000)


class Order(Base):
    __tablename__ = "paper_order"
    __table_args__ = (UniqueConstraint("user_id", "idempotency_key"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("user.id"), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(100))
    symbol: Mapped[str] = mapped_column(String(30))
    side: Mapped[str] = mapped_column(String(4))
    quantity: Mapped[int] = mapped_column(Integer)
    price: Mapped[float] = mapped_column(Numeric(18, 2))
    state: Mapped[str] = mapped_column(String(20), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    filled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Position(Base):
    __tablename__ = "paper_position"
    __table_args__ = (UniqueConstraint("user_id", "symbol"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("user.id"), index=True)
    symbol: Mapped[str] = mapped_column(String(30))
    quantity: Mapped[int] = mapped_column(Integer, default=0)
    average_price: Mapped[float] = mapped_column(Numeric(18, 2), default=0)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("user.id"), index=True)
    action: Mapped[str] = mapped_column(String(80))
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SupportTicket(Base):
    __tablename__ = "support_ticket"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("user.id"), index=True)
    subject: Mapped[str] = mapped_column(String(160))
    message: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
