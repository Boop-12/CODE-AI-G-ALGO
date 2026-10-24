import uuid
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Table
from sqlalchemy import Uuid as UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.session import Base

user_role_table = Table(
    "user_role",
    Base.metadata,
    Column("user_id", UUID(as_uuid=True), ForeignKey("user.id"), primary_key=True),
    Column("role_id", UUID(as_uuid=True), ForeignKey("role.id"), primary_key=True)
)

class User(Base):
    __tablename__ = "user"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    roles = relationship("Role", secondary=user_role_table, back_populates="users")
    refresh_tokens = relationship("RefreshToken", back_populates="user", cascade="all, delete-orphan")
    reset_tokens = relationship("PasswordResetToken", back_populates="user", cascade="all, delete-orphan")

class Role(Base):
    __tablename__ = "role"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, unique=True, index=True, nullable=False)

    users = relationship("User", secondary=user_role_table, back_populates="roles")
