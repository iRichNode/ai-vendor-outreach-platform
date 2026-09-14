from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from app.models.enums import AIReplyMode


class FollowUpItem(BaseModel):
    days_after: float = Field(gt=0, le=365)
    subject: str = Field(min_length=1, max_length=512)
    body: str = Field(min_length=1)


class CampaignCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    initial_email_subject: str = Field(min_length=1, max_length=512)
    initial_email_body: str = Field(min_length=1)
    ai_instructions: str | None = None
    qualification_questions: list[str] | None = None
    follow_ups: list[FollowUpItem] = []
    batch_size: int = Field(default=1, ge=1, le=100)
    min_delay_minutes: int = Field(default=5, ge=1, le=1440)
    max_delay_minutes: int = Field(default=12, ge=1, le=1440)
    daily_max: int = Field(default=30, ge=1, le=1000)
    sending_start_time: str | None = None  # "09:00"
    sending_end_time: str | None = None  # "17:00"
    sending_days: list[int] | None = None  # ISO 1=Mon .. 7=Sun
    timezone: str = "America/New_York"
    ai_reply_mode: AIReplyMode = AIReplyMode.DELAYED
    ai_reply_min_delay_minutes: int = Field(default=3, ge=0, le=1440)
    ai_reply_max_delay_minutes: int = Field(default=10, ge=0, le=1440)
    vendor_ids: list[str] = []

    @model_validator(mode="after")
    def _validate_delays(self):
        if self.max_delay_minutes < self.min_delay_minutes:
            raise ValueError("max_delay_minutes must be >= min_delay_minutes")
        if self.ai_reply_max_delay_minutes < self.ai_reply_min_delay_minutes:
            raise ValueError("ai_reply_max_delay_minutes must be >= ai_reply_min_delay_minutes")
        if self.sending_start_time and self.sending_end_time and not (self.sending_start_time < self.sending_end_time):
            raise ValueError("sending_start_time must be earlier than sending_end_time")
        return self


class CampaignPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    initial_email_subject: str | None = None
    initial_email_body: str | None = None
    ai_instructions: str | None = None
    qualification_questions: list[str] | None = None
    follow_ups: list[FollowUpItem] | None = None
    batch_size: int | None = Field(default=None, ge=1, le=100)
    min_delay_minutes: int | None = Field(default=None, ge=1, le=1440)
    max_delay_minutes: int | None = Field(default=None, ge=1, le=1440)
    daily_max: int | None = Field(default=None, ge=1, le=1000)
    sending_start_time: str | None = None
    sending_end_time: str | None = None
    sending_days: list[int] | None = None
    timezone: str | None = None
    ai_reply_mode: AIReplyMode | None = None
    ai_reply_min_delay_minutes: int | None = None
    ai_reply_max_delay_minutes: int | None = None


class CampaignStatePatch(BaseModel):
    action: str  # activate | pause | resume | archive | complete


class CampaignAddVendors(BaseModel):
    vendor_ids: list[str] = Field(min_length=1)
    auto_approve: bool = True