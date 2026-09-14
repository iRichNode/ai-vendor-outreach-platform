from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPkMixin


class Conversation(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "conversations"

    vendor_id: Mapped[str] = mapped_column(ForeignKey("vendors.id", ondelete="CASCADE"), nullable=False, index=True)
    campaign_id: Mapped[str | None] = mapped_column(ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True, index=True)
    email_account_id: Mapped[str | None] = mapped_column(ForeignKey("email_accounts.id", ondelete="SET NULL"), nullable=True, index=True)

    gmail_thread_id: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True, index=True)
    gmail_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    subject: Mapped[str | None] = mapped_column(String(512), nullable=True)

    status: Mapped[str] = mapped_column(String(32), default="ACTIVE", nullable=False, index=True)
    ai_paused: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    human_controlled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    handoff_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    qualification_status: Mapped[str] = mapped_column(String(32), default="UNQUALIFIED", nullable=False)

    last_inbound_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_outbound_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_follow_up_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    follow_up_step: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    vendor = relationship("Vendor", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")
    meetings = relationship("Meeting", back_populates="conversation", cascade="all, delete-orphan")