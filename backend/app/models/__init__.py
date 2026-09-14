"""ORM models. Importing this package registers every model on Base.metadata."""
from app.models.audit_log import AuditLog
from app.models.campaign import Campaign, CampaignVendor
from app.models.conversation import Conversation
from app.models.email_account import EmailAccount
from app.models.job import ScheduledJob
from app.models.meeting import Meeting
from app.models.message import Message
from app.models.notification import Notification
from app.models.oauth_credential import OAuthCredential
from app.models.settings import AppSetting
from app.models.user import User
from app.models.vendor import Vendor

all_models = [
    User,
    Vendor,
    Campaign,
    CampaignVendor,
    Conversation,
    Message,
    ScheduledJob,
    EmailAccount,
    Meeting,
    Notification,
    AuditLog,
    AppSetting,
    OAuthCredential,
]

__all__ = [
    "User",
    "Vendor",
    "Campaign",
    "CampaignVendor",
    "Conversation",
    "Message",
    "ScheduledJob",
    "EmailAccount",
    "Meeting",
    "Notification",
    "AuditLog",
    "AppSetting",
    "OAuthCredential",
    "all_models",
]