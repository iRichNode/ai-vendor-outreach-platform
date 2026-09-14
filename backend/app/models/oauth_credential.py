"""OAuth credentials (e.g. Gmail) stored encrypted at rest."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPkMixin


class OAuthCredential(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "oauth_credentials"

    provider: Mapped[str] = mapped_column(String(32), nullable=False, index=True)  # gmail
    account_email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    scope: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    # Fernet-encrypted JSON blob (never exposed via API)
    token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)