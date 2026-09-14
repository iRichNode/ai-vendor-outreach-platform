from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPkMixin
from app.models.enums import QualificationStatus, VendorSource, VendorStatus


class Vendor(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "vendors"

    company: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    contact_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    website: Mapped[str | None] = mapped_column(String(512), nullable=True)
    address: Mapped[str | None] = mapped_column(String(512), nullable=True)
    city: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    state: Mapped[str | None] = mapped_column(String(64), nullable=True)
    country: Mapped[str | None] = mapped_column(String(64), nullable=True)
    trade: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    source: Mapped[str] = mapped_column(String(32), default=VendorSource.MANUAL.value, nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[str | None] = mapped_column(String(512), nullable=True)  # comma separated
    research_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(String(32), default=VendorStatus.NEW.value, nullable=False, index=True)
    qualification_status: Mapped[str] = mapped_column(
        String(32), default=QualificationStatus.UNQUALIFIED.value, nullable=False
    )
    last_contacted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_reply_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    opted_out: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    opted_out_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    bounced: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    bounced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    email_unsubscribed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    ai_paused: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    human_handoff: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    meeting_status: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # dedup helpers
    email_domain: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    normalized_email: Mapped[str | None] = mapped_column(String(320), nullable=True, index=True)
    company_loc_key: Mapped[str | None] = mapped_column(String(512), nullable=True, index=True)

    conversations = relationship("Conversation", back_populates="vendor", cascade="all, delete-orphan")
    meetings = relationship("Meeting", back_populates="vendor", cascade="all, delete-orphan")
    jobs = relationship("ScheduledJob", back_populates="vendor", cascade="all, delete-orphan")