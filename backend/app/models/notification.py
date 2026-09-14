from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPkMixin


class Notification(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "notifications"

    notification_type: Mapped[str] = mapped_column(String(32), default="INFO", nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    vendor_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    conversation_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    severity: Mapped[str] = mapped_column(String(16), default="info", nullable=False)
    read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    telegram_sent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    telegram_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    link: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)