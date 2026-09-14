"""CSV preview/validation/import and pasted-list parsing for vendors."""
from __future__ import annotations

import csv
import hashlib
import io
import re
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.vendor_service import create_vendor, find_duplicate_vendor, normalize_email, normalize_website

EXPECTED_COLUMNS = [
    "company", "contact_name", "email", "phone", "website", "city", "state",
    "country", "trade", "notes",
]

COLUMN_ALIASES = {
    "company": ["company", "business", "name", "vendor", "organization", "org", "company_name", "business name"],
    "contact_name": ["contact_name", "contact", "name", "contact name", "full name", "first name", "person"],
    "email": ["email", "e-mail", "email address", "email_address", "mail"],
    "phone": ["phone", "telephone", "phone number", "tel", "mobile", "phone_number"],
    "website": ["website", "web", "url", "site", "web address", "website url", "domain"],
    "city": ["city", "town", "location"],
    "state": ["state", "province", "region", "state/province"],
    "country": ["country", "nation"],
    "trade": ["trade", "industry", "category", "niche", "type", "business type", "specialty"],
    "notes": ["notes", "note", "comments", "description"],
}


@dataclass
class ParsedRow:
    index: int
    data: dict
    errors: list[str] = field(default_factory=list)
    duplicate: bool = False
    duplicate_of: str | None = None

    @property
    def row_hash(self) -> str:
        raw = "|".join(f"{k}={v}" for k, v in sorted(self.data.items()) if v)
        return hashlib.sha1(raw.encode()).hexdigest()[:16]

    @property
    def ok(self) -> bool:
        return not self.errors and not self.duplicate


def _clean_row(raw: dict[str, str], header_map: dict[str, str]) -> dict:
    out: dict[str, str] = {}
    for canonical, value in raw.items():
        mapped = header_map.get(canonical.lower().strip())
        if mapped:
            out[mapped] = (value or "").strip()
    for col in EXPECTED_COLUMNS:
        out.setdefault(col, "")
    return out


def resolve_header(header: str) -> str | None:
    key = header.lower().strip()
    for canonical, aliases in COLUMN_ALIASES.items():
        if key in aliases or key == canonical:
            return canonical
    return None


def parse_csv(content: str) -> tuple[list[dict], list[str]]:
    """Return (rows as list of dicts with canonical keys, global errors)."""
    reader = csv.DictReader(io.StringIO(content))
    header = reader.fieldnames or []
    if not header:
        return [], ["CSV is empty"]
    header_map: dict[str, str] = {}
    unknown: list[str] = []
    for h in header:
        canonical = resolve_header(h)
        if canonical:
            header_map[h] = canonical
        else:
            unknown.append(h)
    rows = [_clean_row(row, header_map) for row in reader]
    return rows, unknown


def parse_pasted(text: str) -> list[dict]:
    """Heuristic parsing for pasted vendor lists.

    Lines may look like:
      - "Company Name <email@example.com>"
      - "Company, email@example.com"
      - "Company | email"
      - "email@example.com, Business Name"
      - plain "email@example.com"
    """
    rows: list[dict] = []
    email_re = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
    for line in text.splitlines():
        line = line.strip().strip(";,")
        if not line:
            continue
        emails = email_re.findall(line)
        email = emails[0] if emails else ""
        rest = email_re.sub("", line).strip(" <>;,\t")
        rest = rest.strip()
        # split remaining text on common separators
        parts = [p.strip() for p in re.split(r"[|,;\t]+", rest) if p.strip()]
        company = parts[0] if parts else None
        contact = parts[1] if len(parts) > 1 and not email else None
        company = company or (line if not email else None)
        if not company and not email:
            continue
        rows.append({
            "company": company or "",
            "contact_name": contact or "",
            "email": email,
            "phone": "",
            "website": "",
            "city": "",
            "state": "",
            "country": "",
            "trade": "",
            "notes": "",
        })
    return rows


async def preview_rows(db: AsyncSession, rows: list[dict], defaults: dict | None = None) -> list[ParsedRow]:
    defaults = defaults or {}
    parsed: list[ParsedRow] = []
    for i, raw in enumerate(rows):
        data = dict(raw)
        for k, v in defaults.items():
            if v and not data.get(k):
                data[k] = v
        errs: list[str] = []
        if not (data.get("company") or "").strip():
            errs.append("Missing company")
        email = normalize_email(data.get("email"))
        if data.get("email") and not email:
            errs.append("Invalid email")
        website = normalize_website(data.get("website"))
        if data.get("website") and website is None:
            errs.append("Invalid website")
        data["email"] = email or ""
        data["website"] = website or ""
        dup = None
        if not errs:
            dup = await find_duplicate_vendor(
                db,
                company=data.get("company") or "",
                email=data.get("email") or None,
                website=data.get("website") or None,
                city=data.get("city"),
                state=data.get("state"),
            )
        parsed.append(
            ParsedRow(
                index=i,
                data=data,
                errors=errs,
                duplicate=bool(dup),
                duplicate_of=dup.company if dup else None,
            )
        )
    return parsed


async def import_rows(db: AsyncSession, rows: list[dict], *, source: str = "CSV") -> tuple[int, list[str]]:
    """Persist only valid, non-duplicate rows. Returns (imported_count, errors)."""
    imported = 0
    errors: list[str] = []
    for raw in rows:
        data = dict(raw)
        try:
            vendor = await create_vendor(db, {**data, "source": source})
            if vendor is not None:
                imported += 1
        except ValueError as exc:
            errors.append(f"Row {raw.get('company', '?')}: {exc}")
    await db.flush()
    return imported, errors