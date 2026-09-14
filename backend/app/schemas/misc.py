from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.enums import NotificationType


class GlobalPausePatch(BaseModel):
    paused: bool


class NotificationReadPatch(BaseModel):
    ids: list[str] | None = None
    all: bool = False


class SettingsSectionPatch(BaseModel):
    """Arbitrary key/value settings for a section (values are JSON-encodable)."""
    section: str = Field(min_length=1, max_length=32)
    values: dict


class TelegramTestResult(BaseModel):
    ok: bool
    detail: str = ""


class RescheduleJob(BaseModel):
    run_after: str  # ISO 8601
    reason: str | None = None
    max_attempts: int | None = None


class DiscoveryRequest(BaseModel):
    query: str = Field(min_length=2, max_length=300)
    limit: int = Field(default=20, ge=1, le=100)
    location: str | None = None


class ResearchRequest(BaseModel):
    vendor_id: str
    max_pages: int = Field(default=4, ge=1, le=10)


class MessageOut(BaseModel):
    id: str
    direction: str
    origin: str
    sender: str
    recipient: str
    subject: str | None = None
    body: str
    received_at: str
    ai_used: bool = False
    delivery_state: str = "SENT"