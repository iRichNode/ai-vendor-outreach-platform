from __future__ import annotations

from pydantic import BaseModel, Field, HttpUrl


class ManualReply(BaseModel):
    body: str = Field(min_length=1, max_length=100_000)
    subject: str | None = Field(default=None, max_length=512)


class AddNote(BaseModel):
    note: str = Field(min_length=1, max_length=50_000)


class MarkInterested(BaseModel):
    interested: bool = True


class MarkQualified(BaseModel):
    qualified: bool = True


class ConversationAction(BaseModel):
    action: str  # pause_ai | resume_ai | take_over | return_to_ai | request_meeting | archive | opt_out
    note: str | None = None


class MeetingLinkIn(BaseModel):
    meeting_url: HttpUrl
    notes: str | None = None


class SendMeetingLink(BaseModel):
    send: bool = True