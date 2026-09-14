"""Domain enums stored as strings in the database."""
from __future__ import annotations

import enum


class StrEnum(str, enum.Enum):
    def __str__(self) -> str:  # pragma: no cover
        return str(self.value)


class VendorStatus(StrEnum):
    NEW = "NEW"
    RESEARCHED = "RESEARCHED"
    READY_TO_CONTACT = "READY_TO_CONTACT"
    CONTACTED = "CONTACTED"
    REPLIED = "REPLIED"
    AI_CONVERSATION = "AI_CONVERSATION"
    INTERESTED = "INTERESTED"
    QUALIFYING = "QUALIFYING"
    QUALIFIED = "QUALIFIED"
    MEETING_REQUESTED = "MEETING_REQUESTED"
    WAITING_FOR_HUMAN_LINK = "WAITING_FOR_HUMAN_LINK"
    MEETING_LINK_RECEIVED = "MEETING_LINK_RECEIVED"
    INVITATION_SENT = "INVITATION_SENT"
    MEETING_SCHEDULED = "MEETING_SCHEDULED"
    HUMAN_HANDOFF = "HUMAN_HANDOFF"
    COMPLETED = "COMPLETED"
    NOT_INTERESTED = "NOT_INTERESTED"
    OPTED_OUT = "OPTED_OUT"
    BOUNCED = "BOUNCED"


class QualificationStatus(StrEnum):
    UNQUALIFIED = "UNQUALIFIED"
    QUALIFYING = "QUALIFYING"
    QUALIFIED = "QUALIFIED"
    NOT_QUALIFIED = "NOT_QUALIFIED"


class VendorSource(StrEnum):
    MANUAL = "MANUAL"
    CSV = "CSV"
    PASTE = "PASTE"
    DISCOVERY = "DISCOVERY"
    RESEARCH = "RESEARCH"


class CampaignStatus(StrEnum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    ARCHIVED = "ARCHIVED"


class ConversationStatus(StrEnum):
    ACTIVE = "ACTIVE"
    HUMAN_CONTROLLED = "HUMAN_CONTROLLED"
    HUMAN_HANDOFF = "HUMAN_HANDOFF"
    WAITING_FOR_HUMAN_LINK = "WAITING_FOR_HUMAN_LINK"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    ARCHIVED = "ARCHIVED"
    CLOSED = "CLOSED"


class MessageDirection(StrEnum):
    INBOUND = "INBOUND"
    OUTBOUND = "OUTBOUND"


class MessageOrigin(StrEnum):
    AI = "AI"
    HUMAN = "HUMAN"
    VENDOR = "VENDOR"
    SYSTEM = "SYSTEM"


class JobType(StrEnum):
    INITIAL_EMAIL = "INITIAL_EMAIL"
    FOLLOW_UP = "FOLLOW_UP"
    AI_REPLY = "AI_REPLY"
    MEETING_INVITATION = "MEETING_INVITATION"


class JobStatus(StrEnum):
    PENDING = "PENDING"
    CLAIMED = "CLAIMED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    PAUSED = "PAUSED"


class MeetingStatus(StrEnum):
    REQUESTED = "REQUESTED"
    WAITING_FOR_LINK = "WAITING_FOR_LINK"
    LINK_RECEIVED = "LINK_RECEIVED"
    INVITATION_SENT = "INVITATION_SENT"
    SCHEDULED = "SCHEDULED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class NotificationType(StrEnum):
    INFO = "INFO"
    INTERESTED = "INTERESTED"
    QUALIFIED = "QUALIFIED"
    MEETING_REQUEST = "MEETING_REQUEST"
    HUMAN_REQUESTED = "HUMAN_REQUESTED"
    AI_NEEDS_HELP = "AI_NEEDS_HELP"
    ERROR = "ERROR"
    SYSTEM = "SYSTEM"


class AIReplyMode(StrEnum):
    IMMEDIATE = "immediate"
    DELAYED = "delayed"


class Intent(StrEnum):
    INTERESTED = "interested"
    NOT_INTERESTED = "not_interested"
    OPT_OUT = "opt_out"
    ASK_QUESTION = "ask_question"
    REQUEST_HUMAN = "request_human"
    REQUEST_MEETING = "request_meeting"
    NEEDS_MORE_INFO = "needs_more_info"
    OTHER = "other"