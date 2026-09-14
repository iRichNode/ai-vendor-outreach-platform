"""Vendor endpoints: CRUD, CSV/paste import, discovery preview, research."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import CurrentUser, JsonRequest
from app.database import get_db
from app.models.vendor import Vendor
from app.schemas.vendor import VendorCreate, VendorPasteIn, VendorPatch, VendorStatusPatch
from app.services import audit, csv_import, discovery, research, vendor_service
from app.services.serializers import serialize_vendor

router = APIRouter(prefix="/vendors", tags=["vendors"])


@router.get("")
async def list_vendors(
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: CurrentUser,
    search: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    trade: str | None = None,
    city: str | None = None,
    opted_out: bool | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict:
    stmt = select(Vendor).order_by(Vendor.created_at.desc())
    count_stmt = select(func.count(Vendor.id))
    if search:
        like = f"%{search}%"
        cond = (
            Vendor.company.ilike(like)
            | Vendor.email.ilike(like)
            | Vendor.contact_name.ilike(like)
            | Vendor.trade.ilike(like)
        )
        stmt = stmt.where(cond)
        count_stmt = count_stmt.where(cond)
    if status_filter:
        stmt = stmt.where(Vendor.status == status_filter)
        count_stmt = count_stmt.where(Vendor.status == status_filter)
    if trade:
        stmt = stmt.where(Vendor.trade == trade)
        count_stmt = count_stmt.where(Vendor.trade == trade)
    if city:
        stmt = stmt.where(Vendor.city == city)
        count_stmt = count_stmt.where(Vendor.city == city)
    if opted_out is not None:
        stmt = stmt.where(Vendor.opted_out == opted_out)
        count_stmt = count_stmt.where(Vendor.opted_out == opted_out)
    total = (await db.execute(count_stmt)).scalar_one()
    vendors = (await db.execute(stmt.limit(limit).offset(offset))).scalars().all()
    return {
        "items": [serialize_vendor(v) for v in vendors],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_vendor(
    body: VendorCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: CurrentUser,
    _json: JsonRequest,
) -> dict:
    try:
        vendor = await vendor_service.create_vendor(db, body.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    await audit.audit(db, actor=_user.username, action="vendor.create", resource_type="vendor", resource_id=vendor.id)
    await db.commit()
    return serialize_vendor(vendor)


@router.get("/meta")
async def vendor_meta(db: Annotated[AsyncSession, Depends(get_db)], _user: CurrentUser) -> dict:
    trades = (
        await db.execute(
            select(distinct(Vendor.trade)).where(Vendor.trade.isnot(None)).order_by(Vendor.trade).limit(200)
        )
    ).scalars().all()
    status_counts = (await db.execute(select(func.count(Vendor.id), Vendor.status).group_by(Vendor.status))).all()
    return {
        "trades": [t for t in trades if t],
        "status_counts": [{"status": s, "count": c} for c, s in status_counts],
    }


@router.get("/{vendor_id}")
async def get_vendor(vendor_id: str, db: Annotated[AsyncSession, Depends(get_db)], _user: CurrentUser) -> dict:
    vendor = await db.get(Vendor, vendor_id)
    if not vendor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vendor not found")
    return serialize_vendor(vendor)


@router.patch("/{vendor_id}")
async def patch_vendor(
    vendor_id: str,
    body: VendorPatch,
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: CurrentUser,
    _json: JsonRequest,
) -> dict:
    vendor = await db.get(Vendor, vendor_id)
    if not vendor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vendor not found")
    data = body.model_dump(exclude_unset=True)
    if data.get("email") is not None:
        data["email"] = vendor_service.normalize_email(data["email"])
        vendor.normalized_email = data["email"]
        vendor.email_domain = vendor_service.email_domain(data["email"])
    elif "email" in data:
        vendor.normalized_email = None
        vendor.email_domain = None
    if data.get("tags") is not None:
        data["tags"] = ",".join(data["tags"])
    for key, value in data.items():
        setattr(vendor, key, value)
    await audit.audit(db, actor=_user.username, action="vendor.update", resource_type="vendor", resource_id=vendor.id,
                      details={"fields": sorted(data.keys())})
    await db.commit()
    return serialize_vendor(vendor)


@router.post("/{vendor_id}/status")
async def patch_vendor_status(
    vendor_id: str,
    body: VendorStatusPatch,
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: CurrentUser,
    _json: JsonRequest,
) -> dict:
    vendor = await db.get(Vendor, vendor_id)
    if not vendor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vendor not found")
    prev = vendor.status
    ok = await vendor_service.transition_vendor(db, vendor, body.status, force=True)
    if not ok:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Invalid status transition")
    await audit.audit(db, actor=_user.username, action="vendor.status", resource_type="vendor", resource_id=vendor.id,
                      details={"from_status": prev, "to_status": body.status})
    await db.commit()
    return serialize_vendor(vendor)


@router.delete("/{vendor_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_vendor(
    vendor_id: str,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: CurrentUser,
    _json: JsonRequest,
) -> Response:
    vendor = await db.get(Vendor, vendor_id)
    if not vendor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vendor not found")
    await db.delete(vendor)
    await audit.audit(db, actor=_user.username, action="vendor.delete", resource_type="vendor", resource_id=vendor.id)
    await db.commit()
    return response


@router.post("/import/csv")
async def import_csv(
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: CurrentUser,
    _json: JsonRequest,
    file: UploadFile = File(...),
    source: str = Form(default="CSV"),
) -> dict:
    content = (await file.read()).decode("utf-8-sig", errors="replace")
    rows, errors = csv_import.parse_csv(content)
    if errors:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": "CSV parse errors", "errors": errors[:50]},
        )
    created, import_errors = await csv_import.import_rows(db, rows, source=source)
    await audit.audit(db, actor=_user.username, action="vendor.import", resource_type="vendor",
                      details={"created": created, "errors": len(import_errors)})
    await db.commit()
    return {"created": created, "errors": import_errors[:50]}


@router.post("/import/paste")
async def import_paste(
    body: VendorPasteIn,
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: CurrentUser,
    _json: JsonRequest,
) -> dict:
    rows = csv_import.parse_pasted(body.text)
    if not rows:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="No vendors parsed from pasted text")
    defaults = {k: v for k, v in {
        "trade": body.trade, "city": body.city, "state": body.state, "country": body.country, "status": body.status
    }.items() if v}
    rows = [{**row, **defaults} for row in rows]
    created, errors = await csv_import.import_rows(db, rows, source="PASTE")
    await audit.audit(db, actor=_user.username, action="vendor.import_paste", resource_type="vendor",
                      details={"created": created, "errors": len(errors)})
    await db.commit()
    return {"created": created, "errors": errors[:50]}


@router.post("/discover")
async def discover_vendors(
    limit: int = Query(default=10, ge=1, le=50),
    db: Annotated[AsyncSession, Depends(get_db)] = None,  # type: ignore[assignment]
    _user: CurrentUser = None,  # type: ignore[assignment]
    _json: JsonRequest = None,  # type: ignore[assignment]
) -> dict:
    """Fetch vendor candidates from the configured discovery provider (demo by default)."""
    items = await discovery.discover_vendors(limit)
    return {"count": len(items), "items": items}


@router.post("/{vendor_id}/research")
async def research_vendor(
    vendor_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: CurrentUser,
    _json: JsonRequest,
) -> dict:
    """Fetch and store a polite one-page research summary for a vendor."""
    vendor = await db.get(Vendor, vendor_id)
    if not vendor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vendor not found")
    website = vendor.website
    if not website:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Vendor has no website to research")
    await vendor_service.transition_vendor(db, vendor, "RESEARCHED", force=True)
    try:
        result = await research.fetch_company_summary(website)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    vendor.research_summary = f"{result['title']}\n\n{result['summary']}"[:5000]
    await audit.audit(db, actor=_user.username, action="vendor.research", resource_type="vendor", resource_id=vendor.id)
    await db.commit()
    return serialize_vendor(vendor)