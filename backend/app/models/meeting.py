from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPkMixin


class Meeting(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "meetings"

    vendor_id: Mapped[str] = mapped_column(ForeignKey("vendors.id", ondelete="CASCADE"), nullable=False, index=True)
    campaign_id: Mapped[str | None] = mapped_column(ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True, index=True)
    conversation_id: Mapped[str | None] = mapped_column(ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True, index=True)
    meeting_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="REQUESTED", nullable=False, index=True)
    requested_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    scheduled_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    invitation_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    vendor = relationship("Vendor", back_populates="meetings")
    conversation = relationship("Conversation", back_populates="meetings")