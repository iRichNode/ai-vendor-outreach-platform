"""Settings endpoints: read/update server-side settings by section."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import CurrentUser, JsonRequest
from app.core.secrets import encrypt_secret
from app.database import get_db
from app.schemas.misc import SettingsSectionPatch
from app.services import settings_service
from app.services.settings_service import DEFAULT_SETTINGS

router = APIRouter(prefix="/settings", tags=["settings"])

# Value returned by GET for a configured secret; also accepted on PUT to mean
# "leave unchanged". Never the real secret.
SECRET_MASK = "********"


def _mask_section(section: str, values: dict) -> dict:
    """Return the same section with configured secrets replaced by the mask."""
    out = dict(values)
    for key, spec in DEFAULT_SETTINGS.get(section, {}).items():
        if spec.get("secret") and out.get(key, "") not in (None, ""):
            out[key] = SECRET_MASK
    return out


def prepare_section_values(section: str, values: dict) -> dict:
    """Validate and normalize a PUT payload for one section (pure, no I/O).

    - Rejects unknown keys with ``HTTPException`` (422).
    - Secret values equal to the mask or empty are dropped ("leave unchanged");
    - New secret values are Fernet-encrypted before they reach the DB.
    """
    known = set(DEFAULT_SETTINGS[section].keys())
    unknown = set(values.keys()) - known
    if unknown:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail=f"Unknown settings keys: {sorted(unknown)}")
    out = dict(values)
    for key, spec in DEFAULT_SETTINGS[section].items():
        if not spec.get("secret"):
            continue
        sent = out.get(key)
        # Empty or the mask means "leave the stored secret unchanged".
        if sent in (None, "", SECRET_MASK):
            out.pop(key, None)
        else:
            out[key] = encrypt_secret(str(sent))
    return out


@router.get("")
async def get_settings(db: Annotated[AsyncSession, Depends(get_db)], _user: CurrentUser) -> dict:
    db_map = await settings_service.get_settings_map(db)
    masked = {section: _mask_section(section, values) for section, values in db_map.items()}
    return {
        "settings": masked,
        "schema": DEFAULT_SETTINGS,
    }


@router.get("/schema")
async def get_settings_schema(_user: CurrentUser) -> dict:
    """Static schema of every editable setting (for rendering the settings form)."""
    return DEFAULT_SETTINGS


@router.put("/{section}")
async def update_settings(
    section: str,
    body: SettingsSectionPatch,
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: CurrentUser,
    _json: JsonRequest,
) -> dict:
    if section != body.section:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="Path section must match body.section")
    if section not in DEFAULT_SETTINGS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown settings section: {section}")
    values = prepare_section_values(section, dict(body.values))
    updated = await settings_service.update_section(db, section, values)
    await db.commit()
    response_section = _mask_section(section, updated.get(section, {}))
    return {"section": section, "settings": response_section}