"""End-to-end API integration tests (live PostgreSQL + Redis, mocked providers).

Runs the full happy path: first-run setup -> login -> vendors -> campaign
create/activate -> queue jobs -> analytics -> settings -> guards.

NOTE: tests share one module-scoped httpx client (and its cookie jar), so the
tests are ordered: unauthenticated guards first, first-run setup second, then the
authenticated flows, and logout last.
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest_asyncio.fixture(scope="module")
async def client() -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://test", follow_redirects=True
    ) as c:
        yield c


async def _post(client: AsyncClient, path: str, json: dict | None = None):
    return await client.post(path, json=json or {}, headers={"X-Requested-With": "XMLHttpRequest"})


async def test_unauthenticated_guard(client: AsyncClient):
    """Must run BEFORE first-run setup: no session cookie exists yet."""
    r = await client.get("/api/vendors")
    assert r.status_code == 401


async def test_first_run_setup(client: AsyncClient):
    r = await client.get("/api/setup/status")
    assert r.status_code == 200
    assert r.json()["setup_required"] is True

    r = await _post(client, "/api/setup/complete",
                    {"username": "admin", "password": "S3cure-Pass!2026", "email": "admin@example.com"})
    assert r.status_code == 201, r.text
    assert r.json()["is_superuser"] is True

    r = await client.get("/api/setup/status")
    assert r.json()["setup_required"] is False


async def test_login_and_me(client: AsyncClient):
    r = await _post(client, "/api/auth/login", {"username": "admin", "password": "S3cure-Pass!2026"})
    assert r.status_code == 200, r.text

    r = await client.get("/api/auth/me")
    body = r.json()
    assert body["authenticated"] is True
    assert body["user"]["username"] == "admin"


async def test_login_rejects_wrong_password(client: AsyncClient):
    r = await _post(client, "/api/auth/login", {"username": "admin", "password": "wrong"})
    assert r.status_code in (401, 403)


async def test_csrf_header_enforced_on_mutating_routes(client: AsyncClient):
    """Authenticated request WITHOUT X-Requested-With on a mutating route -> 403."""
    r = await client.post("/api/vendors", json={"company": "NoCsrf", "email": "x@x.com"})
    assert r.status_code == 403, r.text


async def test_vendor_crud(client: AsyncClient):
    vendors = [
        {"company": "Acme Analytics", "email": "sales@acmeanalytics.com", "contact_name": "Sam",
         "trade": "Analytics", "city": "Austin"},
        {"company": "BlueWave CRM", "email": "hello@bluewavecrm.com", "contact_name": "Rita",
         "trade": "CRM", "city": "Denver"},
    ]
    ids = []
    for v in vendors:
        r = await _post(client, "/api/vendors", v)
        assert r.status_code == 201, r.text
        ids.append(r.json()["id"])

    r = await client.get("/api/vendors")
    assert r.status_code == 200
    assert r.json()["total"] >= 2

    # duplicate rejected
    r = await _post(client, "/api/vendors", vendors[0])
    assert r.status_code == 409

    # patch + status change
    r = await client.patch(f"/api/vendors/{ids[0]}", json={"trade": "Analytics Suite"},
                           headers={"X-Requested-With": "XMLHttpRequest"})
    assert r.status_code == 200
    r = await _post(client, f"/api/vendors/{ids[0]}/status", {"status": "RESEARCHED"})
    assert r.status_code == 200
    assert r.json()["status"] == "RESEARCHED"


async def test_vendor_discovery_demo_provider(client: AsyncClient):
    r = await _post(client, "/api/vendors/discover?limit=5")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] > 0 and len(body["items"]) > 0


async def test_campaign_lifecycle_and_queue(client: AsyncClient):
    r = await client.get("/api/vendors")
    all_vendors = r.json()["items"]
    ids = [v["id"] for v in all_vendors[:2]]

    r = await _post(client, "/api/campaigns", {
        "name": "Q4 Outreach",
        "initial_email_subject": "Intro",
        "initial_email_body": "Hi {{first_name}}, would love to connect.",
        "vendor_ids": ids,
        "timezone": "America/New_York",
    })
    assert r.status_code == 201, r.text
    camp = r.json()
    cid = camp["id"]
    assert camp["status"] == "DRAFT"
    assert camp["vendor_count"] == 2

    # patch
    r = await client.patch(f"/api/campaigns/{cid}", json={"initial_email_subject": "Updated Intro"},
                           headers={"X-Requested-With": "XMLHttpRequest"})
    assert r.status_code == 200

    # activate -> jobs enqueued
    r = await _post(client, f"/api/campaigns/{cid}/state", {"action": "activate"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "ACTIVE"

    r = await client.get("/api/queue/stats")
    stats = r.json()
    assert stats["total"] >= 2
    assert stats["pending"] >= 2

    r = await client.get("/api/queue")
    assert r.status_code == 200
    assert len(r.json()["items"]) >= 2

    # pause campaign -> jobs paused
    await _post(client, f"/api/campaigns/{cid}/state", {"action": "pause"})
    r = await client.get("/api/queue/stats")
    assert r.json()["paused"] >= 2

    # resume
    await _post(client, f"/api/campaigns/{cid}/state", {"action": "resume"})
    r = await client.get("/api/queue/stats")
    assert r.json()["paused"] == 0

    # global pause toggle
    r = await _post(client, "/api/queue/global-pause", {"paused": True})
    assert r.json()["paused"] is True
    r = await _post(client, "/api/queue/global-pause", {"paused": False})
    assert r.json()["paused"] is False


async def test_analytics_endpoints(client: AsyncClient):
    r = await client.get("/api/analytics/dashboard")
    assert r.status_code == 200, r.text
    assert r.json()["total_vendors"] >= 2

    r = await client.get("/api/analytics/funnel")
    assert r.status_code == 200

    r = await client.get("/api/analytics/summary")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "overall" in body and "campaigns" in body

    r = await client.get("/api/dashboard")
    assert r.status_code == 200
    assert "metrics" in r.json()


async def test_settings_roundtrip(client: AsyncClient):
    r = await client.get("/api/settings")
    assert r.status_code == 200
    settings = r.json()["settings"]
    assert "general" in settings

    r = await client.get("/api/settings/schema")
    assert r.status_code == 200

    section = "general"
    payload = {"section": section, "values": {"app_name": "AI Vendor Outreach"}}
    r = await client.put(f"/api/settings/{section}", json=payload,
                         headers={"X-Requested-With": "XMLHttpRequest"})
    assert r.status_code == 200, r.text

    r = await client.get("/api/settings")
    assert r.json()["settings"]["general"]["app_name"] == "AI Vendor Outreach"


async def test_integrations_and_misc(client: AsyncClient):
    r = await client.get("/api/integrations/gmail/status")
    assert r.status_code == 200

    r = await client.get("/api/integrations/telegram/status")
    assert r.status_code == 200

    r = await client.get("/api/conversations")
    assert r.status_code == 200

    r = await client.get("/api/meetings")
    assert r.status_code == 200

    r = await client.get("/api/notifications/unread-count")
    assert r.status_code == 200


async def test_404s(client: AsyncClient):
    assert (await client.get("/api/vendors/does-not-exist")).status_code == 404
    assert (await client.get("/api/campaigns/does-not-exist")).status_code == 404


async def test_logout(client: AsyncClient):
    r = await _post(client, "/api/auth/logout", {})
    assert r.status_code == 204, r.text
    r = await client.get("/api/auth/me")
    assert r.json()["authenticated"] is False