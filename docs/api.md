# API reference

Base URL: `/api` (behind the reverse proxy) or `http://<host>:8000/api` when
running the API directly. Interactive docs: `/api/docs` (Swagger UI) and
schema at `/api/openapi.json`.

## 1. Authentication

- **Login**: `POST /api/auth/login` with JSON
  `{"username": "...", "password": "..."}`. On success the API sets an
  **HttpOnly, SameSite** cookie (`session` by default) — browsers send it
  automatically.
- **Alternative**: `Authorization: Bearer <token>` header with the same session
  token (for non-browser clients and scripts).
- **Logout**: `POST /api/auth/logout`.
- **CSRF defence in depth**: all state-changing JSON endpoints require the
  header `X-Requested-With: XMLHttpRequest` (403 otherwise). SameSite=Lax alone
  already blocks cross-site cookie delivery; the header covers older browsers
  and cross-origin XHR tricks.

Error responses use the FastAPI convention:
`{"detail": "<message>"}`; authentication failures return 401.

## 2. Health endpoints (no auth)

| Endpoint | Meaning | Status codes |
|---|---|---|
| `GET /health` (also at root `/health`) | Liveness: process is up | 200 |
| `GET /ready` (also at root `/ready`) | Readiness: DB + Redis reachable | 200 ok / 503 `{"status":"degraded","database":...,"redis":...,"problems":[...]}` |

## 3. Endpoint map

All routes below are prefixed with `/api`. Auth required unless noted.

### Auth & setup
| Method | Path | Purpose |
|---|---|---|
| POST | `/auth/login` | Log in, set session cookie |
| POST | `/auth/logout` | Invalidate session |
| GET | `/auth/me` | Current user profile |
| GET/POST | `/setup` | First-run setup / wizard state (no auth until admin exists) |

### Dashboard & analytics
| Method | Path | Purpose |
|---|---|---|
| GET | `/dashboard/summary` | KPIs for the home page |
| GET | `/analytics/overview` | Send volume, reply rate, meetings, funnel |
| GET | `/analytics/funnel` | Campaign → contacted → replied → meeting funnel |

### Vendors
| Method | Path | Purpose |
|---|---|---|
| GET | `/vendors` | List/filter/search, pagination |
| POST | `/vendors` | Create (single) |
| GET/PATCH/DELETE | `/vendors/{id}` | Read, update, delete |
| POST | `/vendors/bulk` | Bulk paste import with duplicate detection |
| POST | `/vendors/import` | CSV import |
| GET | `/vendors/discovery/providers` | Available discovery providers |
| POST | `/vendors/discover` | Run provider-based discovery |
| POST | `/vendors/research` | Website research (politeness-limited) |

### Campaigns
| Method | Path | Purpose |
|---|---|---|
| GET/POST | `/campaigns` | List/create |
| GET/PATCH/DELETE | `/campaigns/{id}` | Read/update/delete |
| POST | `/campaigns/{id}/add-vendors` | Attach vendors |
| POST | `/campaigns/{id}/start` / `pause` / `resume` | Lifecycle control |
| GET/PATCH | `/campaigns/{id}/vendors/{vendor_id}` | Per-vendor state, opt-out, pause |

### Conversations & meetings
| Method | Path | Purpose |
|---|---|---|
| GET | `/conversations` | List threads |
| GET | `/conversations/{id}` | Thread with messages |
| POST | `/conversations/{id}/messages` | Send a message (human reply) |
| POST | `/conversations/{id}/takeover` | Human takeover |
| PATCH | `/conversations/{id}` | Change AI/manual mode, summary |
| GET/POST | `/meetings` | List/request meetings |
| PATCH | `/meetings/{id}` | Set URL, reschedule, complete, cancel |

### Queue & ops
| Method | Path | Purpose |
|---|---|---|
| GET | `/queue` | `scheduled_jobs` view (pending/in-flight/recent) |
| POST | `/queue/retry` | Retry a failed job |
| POST | `/queue/cancel` | Cancel a pending job |
| GET | `/notifications` | In-app notifications |

### Integrations & settings
| Method | Path | Purpose |
|---|---|---|
| GET/POST | `/integrations/gmail/auth-url` | Gmail OAuth start |
| GET | `/integrations/gmail/callback` | Gmail OAuth callback |
| POST | `/integrations/gmail/disconnect` | Revoke/remove token |
| GET | `/integrations/status` | Status of each integration |
| GET/PATCH | `/settings` | App settings (pacing defaults, business hours, …) |

> This is a reference summary; the Swagger UI at `/api/docs` is authoritative
> for schemas, query parameters, and pagination conventions.

## 4. Conventions

- **Pagination**: list endpoints accept `page`/`page_size` (or `limit`/`offset`);
  responses include `total` and a `items` (or `results`) array.
- **Timestamps**: ISO 8601 UTC strings.
- **IDs**: UUID strings.
- **State machines**: campaigns `draft → active → paused → completed`;
  vendors `NEW → RESEARCHED → READY_TO_CONTACT → CONTACTED → REPLIED → …`
  (see `backend/app/models/enums.py` for the authoritative lists).
- **Audit**: admin/sensitive operations append to `audit_logs` (visible with
  the audit service; not exposed as a public endpoint).

## 5. Rate limiting

Auth and a few sensitive endpoints are rate-limited via Redis
(`backend/app/core/ratelimit.py`). Exceeding the limit returns 429. Limits are
per-IP (and per-user where noted).