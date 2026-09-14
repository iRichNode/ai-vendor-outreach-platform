from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPkMixin


class Message(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "messages"

    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    vendor_id: Mapped[str] = mapped_column(ForeignKey("vendors.id", ondelete="CASCADE"), nullable=False, index=True)

    gmail_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    gmail_thread_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    # Global/stored idempotency key: "messageId" for inbound; f"out-{job_id}" for outbound
    idempotency_key: Mapped[str] = mapped_column(String(512), nullable=False, unique=True, index=True)

    sender: Mapped[str] = mapped_column(String(512), nullable=False)
    recipient: Mapped[str] = mapped_column(String(512), nullable=False)
    subject: Mapped[str | None] = mapped_column(String(512), nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    body_html: Mapped[str | None] = mapped_column(Text, nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    direction: Mapped[str] = mapped_column(String(16), nullable=False)  # INBOUND / OUTBOUND
    origin: Mapped[str] = mapped_column(String(16), nullable=False)  # AI / HUMAN / VENDOR / SYSTEM
    delivery_state: Mapped[str] = mapped_column(String(32), default="SENT", nullable=False)
    ai_used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    draft: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    conversation = relationship("Conversation", back_populates="messages")