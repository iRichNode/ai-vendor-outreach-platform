"""ORM -> API dict serializers (single source for response shapes)."""
from __future__ import annotations

from typing import Any

from app.models.conversation import Conversation
from app.models.email_account import EmailAccount
from app.models.job import ScheduledJob
from app.models.meeting import Meeting
from app.models.message import Message
from app.models.notification import Notification
from app.models.user import User
from app.models.vendor import Vendor


def _iso(value: Any) -> str | None:
    return value.isoformat() if value is not None else None


def serialize_vendor(vendor: Vendor, *, campaign_status: str | None = None) -> dict[str, Any]:
    return {
        "id": vendor.id,
        "company": vendor.company,
        "contact_name": vendor.contact_name,
        "email": vendor.email,
        "phone": vendor.phone,
        "website": vendor.website,
        "address": vendor.address,
        "city": vendor.city,
        "state": vendor.state,
        "country": vendor.country,
        "trade": vendor.trade,
        "source": vendor.source,
        "source_url": vendor.source_url,
        "notes": vendor.notes,
        "tags": [t for t in (vendor.tags or "").split(",") if t],
        "research_summary": vendor.research_summary,
        "status": vendor.status,
        "qualification_status": vendor.qualification_status,
        "last_contacted_at": _iso(vendor.last_contacted_at),
        "last_reply_at": _iso(vendor.last_reply_at),
        "opted_out": vendor.opted_out,
        "opted_out_at": _iso(vendor.opted_out_at),
        "bounced": vendor.bounced,
        "bounced_at": _iso(vendor.bounced_at),
        "ai_paused": vendor.ai_paused,
        "human_handoff": vendor.human_handoff,
        "meeting_status": vendor.meeting_status,
        "campaign_status": campaign_status,
        "created_at": _iso(vendor.created_at),
        "updated_at": _iso(vendor.updated_at),
    }


def serialize_conversation(conversation: Conversation, *, message_count: int | None = None) -> dict[str, Any]:
    return {
        "id": conversation.id,
        "vendor_id": conversation.vendor_id,
        "campaign_id": conversation.campaign_id,
        "email_account_id": conversation.email_account_id,
        "gmail_thread_id": conversation.gmail_thread_id,
        "gmail_message_id": conversation.gmail_message_id,
        "subject": conversation.subject,
        "status": conversation.status,
        "ai_paused": conversation.ai_paused,
        "human_controlled": conversation.human_controlled,
        "handoff_reason": conversation.handoff_reason,
        "qualification_status": conversation.qualification_status,
        "last_inbound_at": _iso(conversation.last_inbound_at),
        "last_outbound_at": _iso(conversation.last_outbound_at),
        "next_follow_up_at": _iso(conversation.next_follow_up_at),
        "follow_up_step": conversation.follow_up_step,
        "archived": conversation.archived,
        "message_count": message_count,
        "created_at": _iso(conversation.created_at),
        "updated_at": _iso(conversation.updated_at),
    }


def serialize_message(message: Message) -> dict[str, Any]:
    return {
        "id": message.id,
        "conversation_id": message.conversation_id,
        "vendor_id": message.vendor_id,
        "sender": message.sender,
        "recipient": message.recipient,
        "subject": message.subject,
        "body": message.body,
        "body_html": message.body_html,
        "received_at": _iso(message.received_at),
        "direction": message.direction,
        "origin": message.origin,
        "delivery_state": message.delivery_state,
        "ai_used": message.ai_used,
        "draft": message.draft,
        "created_at": _iso(message.created_at),
    }


def serialize_meeting(meeting: Meeting) -> dict[str, Any]:
    return {
        "id": meeting.id,
        "vendor_id": meeting.vendor_id,
        "campaign_id": meeting.campaign_id,
        "conversation_id": meeting.conversation_id,
        "meeting_url": meeting.meeting_url,
        "status": meeting.status,
        "requested_time": _iso(meeting.requested_time),
        "scheduled_time": _iso(meeting.scheduled_time),
        "notes": meeting.notes,
        "invitation_sent_at": _iso(meeting.invitation_sent_at),
        "created_at": _iso(meeting.created_at),
        "updated_at": _iso(meeting.updated_at),
    }


def serialize_job(job: ScheduledJob) -> dict[str, Any]:
    return {
        "id": job.id,
        "job_type": job.job_type,
        "vendor_id": job.vendor_id,
        "campaign_id": job.campaign_id,
        "conversation_id": job.conversation_id,
        "idempotency_key": job.idempotency_key,
        "status": job.status,
        "attempts": job.attempts,
        "max_attempts": job.max_attempts,
        "last_error": job.last_error,
        "run_after": _iso(job.run_after),
        "started_at": _iso(job.started_at),
        "completed_at": _iso(job.completed_at),
        "step": job.step,
        "created_at": _iso(job.created_at),
    }


def serialize_notification(notification: Notification) -> dict[str, Any]:
    return {
        "id": notification.id,
        "notification_type": notification.notification_type,
        "title": notification.title,
        "body": notification.body,
        "severity": notification.severity,
        "read": notification.read,
        "telegram_sent": notification.telegram_sent,
        "telegram_error": notification.telegram_error,
        "vendor_id": notification.vendor_id,
        "conversation_id": notification.conversation_id,
        "link": notification.link,
        "event_time": _iso(notification.event_time),
        "created_at": _iso(notification.created_at),
    }


def serialize_user(user: User) -> dict[str, Any]:
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "is_active": user.is_active,
        "is_superuser": user.is_superuser,
        "last_login_at": _iso(user.last_login_at),
        "created_at": _iso(user.created_at),
    }


def serialize_email_account(account: EmailAccount) -> dict[str, Any]:
    return {
        "id": account.id,
        "email": account.email,
        "display_name": account.display_name,
        "is_active": account.is_active,
        "scope": account.scope,
        "last_sync_at": _iso(account.last_sync_at),
        "last_sync_error": account.last_sync_error,
        # tokens intentionally never serialized
        "created_at": _iso(account.created_at),
    }