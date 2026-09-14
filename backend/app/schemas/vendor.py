from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.models.enums import QualificationStatus


class VendorCreate(BaseModel):
    company: str = Field(min_length=1, max_length=255)
    contact_name: str | None = Field(default=None, max_length=255)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=64)
    website: str | None = Field(default=None, max_length=512)
    address: str | None = Field(default=None, max_length=512)
    city: str | None = Field(default=None, max_length=128)
    state: str | None = Field(default=None, max_length=64)
    country: str | None = Field(default=None, max_length=64)
    trade: str | None = Field(default=None, max_length=128)
    source: str = "MANUAL"
    source_url: str | None = Field(default=None, max_length=1024)
    notes: str | None = None
    tags: list[str] | None = None
    status: str | None = None

    @field_validator("website")
    @classmethod
    def _validate_website(cls, v: str | None) -> str | None:
        if not v:
            return v
        v = v.strip()
        if not re.match(r"^https?://", v) and "." in v:
            v = f"https://{v}"
        if not re.match(r"^https?://[^\s]+", v):
            raise ValueError("Website must be a valid http(s) URL")
        return v


class VendorPatch(BaseModel):
    company: str | None = Field(default=None, min_length=1, max_length=255)
    contact_name: str | None = Field(default=None, max_length=255)
    email: EmailStr | None = None
    phone: str | None = None
    website: str | None = None
    address: str | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None
    trade: str | None = None
    notes: str | None = None
    tags: list[str] | None = None
    research_summary: str | None = None

    @model_validator(mode="after")
    def _at_least_one(self):
        changed = self.model_dump(exclude_unset=True)
        if not changed:
            raise ValueError("At least one field must be provided")
        return self


class VendorStatusPatch(BaseModel):
    status: str


class VendorPasteIn(BaseModel):
    """Pasted text: one vendor per line. Lines look like:
    Company <email@example.com>
    Company, contact@example.com
    Company | email
    name@example.com,business
    """
    text: str = Field(min_length=1, max_length=200_000)
    trade: str | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None
    status: str | None = None


class CsvImportPreviewRequest(BaseModel):
    """Preview a CSV without persisting. Rows come back with validation status."""
    content: str = Field(min_length=1, max_length=5_000_000)
    filename: str | None = None


class CsvImportConfirm(BaseModel):
    """Persist previously previewed rows (by row hash)."""
    preview_id: str
    rows: list[dict]
    trade: str | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None
    tags: list[str] | None = None
    status: str | None = None


class VendorSearch(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    company: str
    contact_name: str | None = None
    email: str | None = None
    phone: str | None = None
    website: str | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None
    trade: str | None = None
    status: str | None = None
    qualification_status: str | None = None
    opted_out: bool = False
    bounced: bool = False