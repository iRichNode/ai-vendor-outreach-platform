"""Campaign endpoints: CRUD, activation, vendor assignment, start."""
from __future__ import annotations

from typing import Annotated

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.auth import CurrentUser, JsonRequest
from app.database import get_db
from app.models.campaign import Campaign, CampaignVendor
from app.models.enums import CampaignStatus
from app.models.vendor import Vendor
from app.schemas.campaign import CampaignAddVendors, CampaignCreate, CampaignPatch, CampaignStatePatch
from app.services import audit, campaign_service, queue_service

router = APIRouter(prefix="/campaigns", tags=["campaigns"])


@router.get("")
async def list_campaigns(
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: CurrentUser,
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict:
    stmt = select(Campaign, func.count(CampaignVendor.id)).outerjoin(
        CampaignVendor, CampaignVendor.campaign_id == Campaign.id
    ).group_by(Campaign.id).order_by(Campaign.created_at.desc())
    if status_filter:
        stmt = stmt.where(Campaign.status == status_filter)
    rows = (await db.execute(stmt.limit(limit).offset(offset))).all()
    count_stmt = select(func.count(Campaign.id))
    if status_filter:
        count_stmt = count_stmt.where(Campaign.status == status_filter)
    total = (await db.execute(count_stmt)).scalar_one()
    items = []
    for campaign, vendor_count in rows:
        data = campaign_service.campaign_to_dict(campaign)
        data["vendor_count"] = vendor_count
        items.append(data)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_campaign(
    body: CampaignCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: CurrentUser,
    _json: JsonRequest,
) -> dict:
    data = body.model_dump(exclude={"vendor_ids", "status", "activate_now"})
    campaign = Campaign(name=data["name"], status=CampaignStatus.DRAFT.value)
    campaign_service.apply_campaign_patch(campaign, data)
    db.add(campaign)
    await db.flush()
    if body.vendor_ids:
        added = await campaign_service.add_vendors_to_campaign(db, campaign, body.vendor_ids)
    else:
        added = 0
    await audit.audit(db, actor=_user.username, action="campaign.create", resource_type="campaign",
                      resource_id=campaign.id, details={"vendors_added": added})
    await db.commit()
    out = campaign_service.campaign_to_dict(campaign)
    out["vendor_count"] = added
    return out


@router.get("/{campaign_id}")
async def get_campaign(campaign_id: str, db: Annotated[AsyncSession, Depends(get_db)], _user: CurrentUser) -> dict:
    campaign = await db.get(Campaign, campaign_id)
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
    vendor_count = (await db.execute(
        select(func.count(CampaignVendor.id)).where(CampaignVendor.campaign_id == campaign_id)
    )).scalar_one()
    pending = await queue_service.count_pending_for(db, campaign_id=campaign_id)
    out = campaign_service.campaign_to_dict(campaign)
    out["vendor_count"] = vendor_count
    out["pending_jobs"] = pending
    return out


@router.patch("/{campaign_id}")
async def patch_campaign(
    campaign_id: str,
    body: CampaignPatch,
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: CurrentUser,
    _json: JsonRequest,
) -> dict:
    campaign = await db.get(
        Campaign, campaign_id, options=[selectinload(Campaign.campaign_vendors)]
    )
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
    data = body.model_dump(exclude_unset=True)
    campaign_service.apply_campaign_patch(campaign, data)
    await audit.audit(db, actor=_user.username, action="campaign.update", resource_type="campaign",
                      resource_id=campaign_id, details={"fields": sorted(data.keys())})
    await db.commit()
    return campaign_service.campaign_to_dict(campaign)


@router.delete("/{campaign_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_campaign(
    campaign_id: str,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: CurrentUser,
    _json: JsonRequest,
) -> Response:
    campaign = await db.get(Campaign, campaign_id)
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
    await db.delete(campaign)
    await audit.audit(db, actor=_user.username, action="campaign.delete", resource_type="campaign", resource_id=campaign_id)
    await db.commit()
    return response


@router.post("/{campaign_id}/vendors")
async def add_vendors(
    campaign_id: str,
    body: CampaignAddVendors,
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: CurrentUser,
    _json: JsonRequest,
) -> dict:
    campaign = await db.get(Campaign, campaign_id)
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
    added = await campaign_service.add_vendors_to_campaign(db, campaign, body.vendor_ids)
    await audit.audit(db, actor=_user.username, action="campaign.add_vendors", resource_type="campaign",
                      resource_id=campaign_id, details={"added": added})
    await db.commit()
    return {"added": added}


@router.get("/{campaign_id}/vendors")
async def list_campaign_vendors(
    campaign_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: CurrentUser,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict:
    campaign = await db.get(Campaign, campaign_id)
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
    stmt = (
        select(Vendor, CampaignVendor.status)
        .join(CampaignVendor, CampaignVendor.vendor_id == Vendor.id)
        .where(CampaignVendor.campaign_id == campaign_id)
        .order_by(Vendor.created_at.desc())
    )
    total = (await db.execute(
        select(func.count(CampaignVendor.id)).where(CampaignVendor.campaign_id == campaign_id)
    )).scalar_one()
    rows = (await db.execute(stmt.limit(limit).offset(offset))).all()
    from app.services.serializers import serialize_vendor

    return {
        "items": [serialize_vendor(v, campaign_status=slot) for v, slot in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.post("/{campaign_id}/state")
async def campaign_state(
    campaign_id: str,
    body: CampaignStatePatch,
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: CurrentUser,
    _json: JsonRequest,
) -> dict:
    campaign = await db.get(Campaign, campaign_id)
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
    action = body.action
    if action == "activate":
        campaign.status = CampaignStatus.ACTIVE.value
        campaign.started_at = campaign.started_at or datetime.now(UTC)
        scheduled = await campaign_service.schedule_initial_emails(db, campaign)
        detail = {"scheduled": scheduled}
    elif action == "pause":
        campaign.status = CampaignStatus.PAUSED.value
        await queue_service.set_paused_all_for_campaign(db, campaign_id)
        detail = {}
    elif action == "resume":
        campaign.status = CampaignStatus.ACTIVE.value
        await queue_service.resume_all_for_campaign(db, campaign_id)
        detail = {}
    elif action == "archive":
        campaign.status = CampaignStatus.ARCHIVED.value
        detail = {}
    elif action == "complete":
        campaign.status = CampaignStatus.COMPLETED.value
        campaign.completed_at = datetime.now(UTC)
        await queue_service.cancel_jobs_for_campaign(db, campaign_id)
        detail = {}
    else:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="action must be one of activate|pause|resume|archive|complete")
    await audit.audit(db, actor=_user.username, action=f"campaign.{action}", resource_type="campaign",
                      resource_id=campaign_id, details=detail)
    await db.commit()
    return campaign_service.campaign_to_dict(campaign)