from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.models.base import Base, TimestampMixin, UUIDPkMixin


class ScheduledJob(UUIDPkMixin, TimestampMixin, Base):
    """Persistent sending queue item.

    The queue is the source of truth (survives worker restarts). Workers claim rows
    atomically; a completed send is only recorded once (idempotency key + status guard).
    """

    __tablename__ = "scheduled_jobs"
    __table_args__ = (
        Index("ix_scheduled_jobs_due_status", "run_after", "status"),
        Index("ix_scheduled_jobs_vendor_type", "vendor_id", "job_type"),
    )

    job_type: Mapped[str] = mapped_column(String(32), nullable=False)  # INITIAL_EMAIL | FOLLOW_UP | AI_REPLY | MEETING_INVITATION
    vendor_id: Mapped[str] = mapped_column(ForeignKey("vendors.id", ondelete="CASCADE"), nullable=False, index=True)
    campaign_id: Mapped[str | None] = mapped_column(ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True, index=True)
    conversation_id: Mapped[str | None] = mapped_column(ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True, index=True)

    idempotency_key: Mapped[str] = mapped_column(String(512), nullable=False, unique=True, index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    run_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="PENDING", nullable=False, index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=6, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    claim_uuid: Mapped[str | None] = mapped_column(String(64), nullable=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # For follow-ups: which follow-up step this job represents
    step: Mapped[int | None] = mapped_column(Integer, nullable=True)

    vendor = relationship("Vendor", back_populates="jobs")
    campaign = relationship("Campaign")