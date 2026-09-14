"""Settings endpoints: read/update server-side settings by section."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import CurrentUser, JsonRequest
from app.database import get_db
from app.schemas.misc import SettingsSectionPatch
from app.services import settings_service
from app.services.settings_service import DEFAULT_SETTINGS

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("")
async def get_settings(db: Annotated[AsyncSession, Depends(get_db)], _user: CurrentUser) -> dict:
    return {
        "settings": await settings_service.get_settings_map(db),
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
    known = set(DEFAULT_SETTINGS[section].keys())
    unknown = set(body.values.keys()) - known
    if unknown:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail=f"Unknown settings keys: {sorted(unknown)}")
    updated = await settings_service.update_section(db, section, body.values)
    await db.commit()
    return {"section": section, "settings": updated.get(section, {})}