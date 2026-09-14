from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.settings import AppSetting

# Server-side settings that the operator may manage from the dashboard.
DEFAULT_SETTINGS: dict[str, dict[str, Any]] = {
    "general": {
        "app_name": {"value": "AI Vendor Outreach", "type": "str"},
        "timezone": {"value": "America/New_York", "type": "str"},
    },
    "ai": {
        "provider": {"value": "openrouter", "type": "str"},
        "model": {"value": "openai/gpt-4o-mini", "type": "str"},
        "temperature": {"value": 0.3, "type": "float"},
        "max_output_tokens": {"value": 900, "type": "int"},
        "instructions": {"value": "", "type": "str"},
    },
    "gmail": {
        "watch_pubsub": {"value": True, "type": "bool"},
    },
    "telegram": {},
    "sending": {
        "batch_size": {"value": 1, "type": "int"},
        "min_delay_minutes": {"value": 5, "type": "int"},
        "max_delay_minutes": {"value": 12, "type": "int"},
        "daily_max": {"value": 30, "type": "int"},
        "sending_hours": {"value": "9-17", "type": "str"},
        "sending_days": {"value": "1,2,3,4,5", "type": "str"},
    },
    "follow_ups": {
        "default_days": {"value": 2, "type": "int"},
    },
    "notifications": {
        "telegram_enabled": {"value": True, "type": "bool"},
        "interest_level": {"value": "interested", "type": "str"},
    },
}


def _coerce(value: Any, value_type: str) -> Any:
    try:
        if value_type == "int":
            return int(value)
        if value_type == "float":
            return float(value)
        if value_type == "bool":
            if isinstance(value, str):
                return value.lower() in {"1", "true", "yes", "on"}
            return bool(value)
        if value_type == "json":
            return value if isinstance(value, (dict, list)) else json.loads(value)
    except (ValueError, TypeError, json.JSONDecodeError):
        return value
    return value


async def ensure_default_settings(db: AsyncSession) -> None:
    existing = (await db.execute(select(AppSetting.key))).scalars().all()
    have = set(existing)
    for section, entries in DEFAULT_SETTINGS.items():
        for key, spec in entries.items():
            full = f"{section}.{key}"
            if full not in have:
                db.add(
                    AppSetting(
                        key=full,
                        value=_serialize(spec["value"]),
                        value_type=spec["type"],
                        section=section,
                    )
                )
    await db.flush()


def _serialize(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value)
    return str(value)


async def get_settings_map(db: AsyncSession) -> dict[str, dict[str, Any]]:
    rows = (await db.execute(select(AppSetting))).scalars().all()
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        section = out.setdefault(row.section, {})
        section[row.key.split(".", 1)[1]] = _coerce(row.value, row.value_type) if row.value is not None else None
    return out


async def update_section(db: AsyncSession, section: str, values: dict[str, Any]) -> dict[str, dict[str, Any]]:
    for key, value in values.items():
        full = f"{section}.{key}"
        row = (await db.execute(select(AppSetting).where(AppSetting.key == full))).scalars().first()
        type_ = DEFAULT_SETTINGS.get(section, {}).get(key, {}).get("type", "str")
        if row is None:
            row = AppSetting(key=full, value=_serialize(value), value_type=type_, section=section)
            db.add(row)
        else:
            row.value = _serialize(value)
            row.value_type = type_
    await db.flush()
    return await get_settings_map(db)