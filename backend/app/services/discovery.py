"""Vendor discovery: demo provider + optional configurable HTTP API.

DISCOVERY_PROVIDER = "demo" (default) returns realistic fake vendors.
DISCOVERY_PROVIDER = "http" calls DISCOVERY_API_URL with
DISCOVERY_API_KEY as a Bearer token. The provider returns a list of
{"company","domain","email","contact_name"} objects.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger("app.services.discovery")


class DiscoveryError(RuntimeError):
    pass


DEMO_COMPANIES = [
    ("Acme Robotics", "acmerobotics.com", "sales@acmerobotics.com", "Jordan Blake"),
    ("Nimbus Analytics", "nimbusanalytics.io", "hello@nimbusanalytics.io", "Priya Sharma"),
    ("Ironforge DevTools", "ironforge.dev", "support@ironforge.dev", "Marcus Chen"),
    ("Helios Cloudworks", "helioscloud.com", "contact@helioscloud.com", "Sofia Reyes"),
    ("Vertex Industrial", "vertexindustrial.com", "info@vertexindustrial.com", "Liam O'Sullivan"),
    ("Cobalt Data Systems", "cobaltdata.systems", "sales@cobaltdata.systems", "Aiko Tanaka"),
    ("Prairie State Logistics", "prairiestatelogistics.com", "ops@prairiestatelogistics.com", "Ethan Miller"),
    ("Bluepeak Security", "bluepeaksecurity.com", "hello@bluepeaksecurity.com", "Amara Diallo"),
    ("Quantum Fabric", "quantumfabric.co", "contact@quantumfabric.co", "Noah Williams"),
    ("Sunset Computing", "sunsetcomputing.com", "info@sunsetcomputing.com", "Chloe Martin"),
    ("Aurora Microsystems", "auroramicro.com", "sales@auroramicro.com", "Diego Fernández"),
    ("Redwood Energy Group", "redwoodenergy.com", "contact@redwoodenergy.com", "Hannah Kim"),
    ("Polar Circuit Labs", "polarlabs.io", "hello@polarlabs.io", "Yusuf Karim"),
    ("Granite Robotics", "graniterobotics.com", "sales@graniterobotics.com", "Ingrid Novak"),
    ("Delta Fulfillment", "deltafulfillment.com", "ops@deltafulfillment.com", "Omar Haddad"),
]


async def discover_vendors(vendors_requested: int = 10) -> list[dict[str, str]]:
    """Discover vendors. Raises DiscoveryError on provider failure."""
    settings = get_settings()
    provider = (settings.DISCOVERY_PROVIDER or "demo").lower()
    if provider == "demo":
        count = max(1, min(vendors_requested or 10, len(DEMO_COMPANIES)))
        return [
            {"company": c, "domain": d, "email": e, "contact_name": n}
            for c, d, e, n in DEMO_COMPANIES[:count]
        ]
    if provider == "http":
        if not settings.DISCOVERY_API_URL:
            raise DiscoveryError("DISCOVERY_PROVIDER=http requires DISCOVERY_API_URL")
        headers = {"Authorization": f"Bearer {settings.DISCOVERY_API_KEY}"} if settings.DISCOVERY_API_KEY else {}
        try:
            async with httpx.AsyncClient(timeout=30, headers=headers) as client:
                resp = await client.get(settings.DISCOVERY_API_URL)
                resp.raise_for_status()
                data = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.error("discovery_http_error detail=%s", str(exc))
            raise DiscoveryError(f"Discovery API failed: {exc}") from exc
        items = data if isinstance(data, list) else data.get("results", data.get("vendors", []))
        normalized: list[dict[str, str]] = []
        for item in items:
            normalized.append(
                {
                    "company": str(item.get("company", "")),
                    "domain": str(item.get("domain", "")),
                    "email": str(item.get("email", "")),
                    "contact_name": str(item.get("contact_name", item.get("name", ""))),
                }
            )
        return normalized[: max(1, min(vendors_requested or len(normalized), 500))]
    raise DiscoveryError(f"Unknown DISCOVERY_PROVIDER: {provider}")


def is_likely_fake(item: dict[str, Any]) -> bool:
    """Heuristic guard: discovery providers must never return real vendor data in demo."""
    company = str(item.get("company", ""))
    email = str(item.get("email", ""))
    if not company and not email:
        return True
    if email.lower().startswith(("admin@", "root@", "postmaster@")):
        return True
    return False