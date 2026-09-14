from __future__ import annotations

from datetime import datetime, time

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, Time, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.models.base import Base, TimestampMixin, UUIDPkMixin, utcnow
from app.models.enums import CampaignStatus


class Campaign(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "campaigns"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default=CampaignStatus.DRAFT.value, nullable=False, index=True)

    initial_email_subject: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    initial_email_body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    ai_instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    qualification_questions: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list of strings

    # Follow-up config: JSON list e.g. [{"days_after": 2, "subject": ..., "body": ...}, ...]
    follow_ups: Mapped[list] = mapped_column(JSON, default=list, nullable=False)

    # Pacing
    batch_size: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    min_delay_minutes: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    max_delay_minutes: Mapped[int] = mapped_column(Integer, default=12, nullable=False)
    daily_max: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    sending_start_time: Mapped[time | None] = mapped_column(Time(timezone=False), nullable=True)
    sending_end_time: Mapped[time | None] = mapped_column(Time(timezone=False), nullable=True)
    sending_days: Mapped[str | None] = mapped_column(String(64), nullable=True)  # "1,2,3,4,5"
    timezone: Mapped[str] = mapped_column(String(64), default="America/New_York", nullable=False)

    # AI reply delay
    ai_reply_mode: Mapped[str] = mapped_column(String(16), default="delayed", nullable=False)
    ai_reply_min_delay_minutes: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    ai_reply_max_delay_minutes: Mapped[int] = mapped_column(Integer, default=10, nullable=False)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    campaign_vendors = relationship("CampaignVendor", back_populates="campaign", cascade="all, delete-orphan")


class CampaignVendor(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "campaign_vendors"
    __table_args__ = (UniqueConstraint("campaign_id", "vendor_id", name="uq_campaign_vendor"),)

    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True)
    vendor_id: Mapped[str] = mapped_column(ForeignKey("vendors.id", ondelete="CASCADE"), nullable=False, index=True)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    # Slot state for this campaign (copy of the vendor's status at campaign level)
    status: Mapped[str] = mapped_column(String(32), default="QUEUED", nullable=False)
    initial_job_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    campaign = relationship("Campaign", back_populates="campaign_vendors")
    vendor = relationship("Vendor")