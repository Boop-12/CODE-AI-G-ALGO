"""Additive provenance for imports from the legacy users table."""
import uuid
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Integer, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base
from app.models.platform import utcnow


class LegacyAccountImport(Base):
    __tablename__ = "legacy_account_import"
    legacy_user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("user.id"), unique=True)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
