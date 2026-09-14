from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPkMixin


class EmailAccount(UUIDPkMixin, TimestampMixin, Base):
    """A connected Gmail account (OAuth 2.0).

    Refresh tokens are stored server-side only, encrypted at rest with Fernet using a
    key derived from SECRET_KEY. They are never exposed through the API.
    """

    __tablename__ = "email_accounts"

    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True, index=True)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    access_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    refresh_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    scope: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    history_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    watch_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    watch_channel: Mapped[str | None] = mapped_column(String(512), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_sync_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    sync_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)