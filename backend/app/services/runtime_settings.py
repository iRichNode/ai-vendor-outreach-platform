"""Runtime credential overrides stored in the settings table.

Operators manage AI / Gmail / SMTP / Telegram credentials from the web panel.
Values live encrypted in the ``settings`` table and are merged here into the
process-level ``Settings`` object on a per-operation basis, so a change in the
panel takes effect on the next job/send without restarting the API or worker.

Map: "section.key" (settings table) -> (env var name, is_secret). Only the keys
in FIELD_MAP are overridable at runtime; everything else always comes from env.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.core.secrets import decrypt_secret
from app.services.settings_service import DEFAULT_SETTINGS, get_settings_map

# section.key -> (Settings attribute name, is_secret)
FIELD_MAP: dict[str, tuple[str, bool]] = {
    # AI provider
    "ai.api_key": ("OPENROUTER_API_KEY", True),
    "ai.base_url": ("OPENROUTER_BASE_URL", False),
    # Gmail OAuth app + sending profile
    "gmail.client_id": ("GOOGLE_CLIENT_ID", False),
    "gmail.client_secret": ("GOOGLE_CLIENT_SECRET", True),
    "gmail.transport": ("GMAIL_TRANSPORT", False),
    "gmail.sender_email": ("GMAIL_SENDER_EMAIL", False),
    "gmail.sender_name": ("GMAIL_SENDER_NAME", False),
    # SMTP (Microsoft 365 / Outlook / any provider)
    "smtp.host": ("SMTP_HOST", False),
    "smtp.port": ("SMTP_PORT", False),
    "smtp.username": ("SMTP_USERNAME", False),
    "smtp.password": ("SMTP_PASSWORD", True),
    "smtp.from_email": ("SMTP_FROM_EMAIL", False),
    "smtp.from_name": ("SMTP_FROM_NAME", False),
    "smtp.use_tls": ("SMTP_USE_TLS", False),
    # Telegram bot
    "telegram.bot_token": ("TELEGRAM_BOT_TOKEN", True),
    "telegram.chat_id": ("TELEGRAM_CHAT_ID", False),
}


def _decrypt(value: Any) -> str:
    """Return plaintext for a stored secret, tolerating legacy plaintext rows."""
    if value is None:
        return ""
    text = str(value)
    if not text:
        return ""
    try:
        return decrypt_secret(text)
    except Exception:  # noqa: BLE001 - legacy plaintext or corrupt value
        return text


def merge_settings(db_map: dict[str, dict[str, Any]], base: Settings | None = None) -> Settings:
    """Merge panel-stored values on top of env-based settings (pure, no I/O).

    ``db_map`` is the section -> {key: value} map returned by
    ``settings_service.get_settings_map``. Secret rows are decrypted first
    (legacy plaintext rows are tolerated). Empty and missing values are
    ignored so environment defaults win for fields the operator never set.
    """
    updates: dict[str, Any] = {}
    for full_key, (field_name, is_secret) in FIELD_MAP.items():
        section, _, key = full_key.partition(".")
        value = db_map.get(section, {}).get(key)
        if value is None or value == "":
            continue
        if is_secret:
            value = _decrypt(value)
            if not value:
                continue
        updates[field_name] = value

    base = base if base is not None else get_settings()
    if not updates:
        return base
    return base.model_copy(update=updates)


async def effective_settings(db: AsyncSession) -> Settings:
    """Fresh ``Settings`` copy with panel-stored credentials merged in.

    Falls back to the base env-based settings for every non-overridden field.
    """
    db_map = await get_settings_map(db)
    return merge_settings(db_map)


def is_secret_setting(section: str, key: str) -> bool:
    """True when the schema declares this setting a masked credential."""
    spec = DEFAULT_SETTINGS.get(section, {}).get(key, {})
    return bool(spec.get("secret"))