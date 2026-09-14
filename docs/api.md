# API reference

Base URL: `/api` (behind the reverse proxy) or `http://<host>:8000/api` when
running the API directly. Interactive docs: `/api/docs` (Swagger UI) and
schema at `/api/openapi.json` — the schema is authoritative and always
up-to-date; the tables below were generated from it.

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
- `GET /api/auth/me` never returns 401: it answers
  `{"authenticated": false, "user": null}` when unauthenticated so the
  dashboard can decide client-side where to redirect.

Error responses use the FastAPI convention:
`{"detail": "<message>"}`; protected endpoints return 401 when the session is
missing/expired.

## 2. Health endpoints (no auth)

| Endpoint | Meaning | Status codes |
|---|---|---|
| `GET /health` (also at root `/health`) | Liveness: process is up | 200 |
| `GET /health/full` (also at root `/ready`) | Readiness: DB + Redis reachable | 200 ok / 503 `{"status":"degraded","database":...,"redis":...,"problems":[...]}` |

## 3. Endpoint map

All routes below are prefixed with `/api`. Auth required unless noted.

### Auth & setup
| Method | Path | Purpose |
|---|---|---|
| POST | `/auth/login` | Log in, set session cookie |
| POST | `/auth/logout` | Invalidate session |
| GET | `/auth/me` | Current user + session status |
| GET | `/setup/status` | Whether initial admin still needs to be created |
| POST | `/setup/complete` | Create the initial admin (only while no users exist) |

### Dashboard & analytics
| Method | Path | Purpose |
|---|---|---|
| GET | `/dashboard` | Aggregate KPIs for the landing page (metrics + counts + global pause) |
| GET | `/analytics/dashboard` | Main analytics dashboard payload |
| GET | `/analytics/summary` | Rolled-up summary numbers |
| GET | `/analytics/funnel` | Campaign → contacted → replied → meeting funnel |

### Vendors
| Method | Path | Purpose |
|---|---|---|
| GET, POST | `/vendors` | List/filter/search (paginated) and create |
| GET, PATCH, DELETE | `/vendors/{vendor_id}` | Read, update, delete |
| POST | `/vendors/import/paste` | Bulk paste import with duplicate detection |
| POST | `/vendors/import/csv` | CSV import |
| POST | `/vendors/discover` | Run provider-based discovery |
| POST | `/vendors/{vendor_id}/research` | Website research for one vendor |
| POST | `/vendors/{vendor_id}/status` | Advance the vendor status workflow |
| GET | `/vendors/meta` | Enumerations (statuses, sources, trades, …) |

### Campaigns
| Method | Path | Purpose |
|---|---|---|
| GET, POST | `/campaigns` | List/create (create accepts `vendor_ids`) |
| GET, PATCH, DELETE | `/campaigns/{campaign_id}` | Read/update/delete |
| POST | `/campaigns/{campaign_id}/state` | Lifecycle: body `{"action": "activate \| pause \| resume \| archive \| complete"}` |
| GET, POST | `/campaigns/{campaign_id}/vendors` | List/attach vendors |

### Conversations & meetings
| Method | Path | Purpose |
|---|---|---|
| GET | `/conversations` | List threads |
| GET | `/conversations/{conversation_id}` | Thread with messages |
| POST | `/conversations/{conversation_id}/messages` | Send a message (human reply) |
| POST | `/conversations/{conversation_id}/action` | Conversation actions (takeover, hand back to AI, …) |
| POST | `/conversations/{conversation_id}/mark-interest` / `mark-qualified` | Qualification flags |
| POST | `/conversations/{conversation_id}/meeting-link` | Operator supplies the meeting URL |
| POST | `/conversations/{conversation_id}/notes` | Add/update operator notes |
| GET | `/meetings` | List meetings |
| GET | `/meetings/{meeting_id}` | Meeting detail |
| POST | `/meetings/{meeting_id}/send-invitation` | Queue invitation email |
| POST | `/meetings/{meeting_id}/mark-scheduled` / `complete` / `cancel` | Outcome transitions |

### Queue & ops
| Method | Path | Purpose |
|---|---|---|
| GET | `/queue` | `scheduled_jobs` view (pending/in-flight/recent) |
| GET | `/queue/stats` | Counts by status + global-pause flag |
| GET, POST | `/queue/global-pause` | Read/set the global pause switch |
| POST | `/queue/purge` | Remove terminal jobs (maintenance) |
| POST | `/queue/{job_id}/cancel` / `pause` / `resume` | Per-job control |
| POST | `/queue/{job_id}/retry` | Retry a failed job |
| POST | `/queue/{job_id}/reschedule` | Move a job to a new target time |
| GET | `/notifications` | In-app notification records |
| POST | `/notifications/read` / `clear` | Mark read / clear |
| GET | `/notifications/unread-count` | Count badge value |

### Integrations & settings
| Method | Path | Purpose |
|---|---|---|
| GET | `/integrations/gmail/auth-url` | Gmail OAuth start (returns auth URL) |
| GET | `/integrations/gmail/callback` | Gmail OAuth callback |
| POST | `/integrations/gmail/disconnect` | Revoke/remove token |
| GET | `/integrations/gmail/status` | Gmail connection status |
| GET | `/integrations/telegram/status` | Telegram bot status |
| POST | `/integrations/telegram/test` | Send a test notification |
| GET | `/settings` | Current settings |
| GET | `/settings/schema` | Settings schema (for the UI form) |
| PUT | `/settings/{section}` | Update a settings section |

> The Swagger UI at `/api/docs` is authoritative for schemas, query
> parameters, and pagination conventions.

## 4. Conventions

- **Pagination**: list endpoints accept `page`/`page_size` (or `limit`/`offset`);
  responses include `total` and an `items` array.
- **Timestamps**: ISO 8601 UTC strings.
- **IDs**: UUID strings.
- **State machines**: campaigns `draft → active → paused/archived → completed`;
  vendors `NEW → RESEARCHED → READY_TO_CONTACT → CONTACTED → REPLIED → …`
  (see `backend/app/models/enums.py` for the authoritative lists).
- **Audit**: admin/sensitive operations append to `audit_logs` (not exposed as
  a public endpoint).

## 5. Rate limiting

Auth and setup endpoints are rate-limited via Redis
(`backend/app/core/ratelimit.py`). Exceeding the limit returns 429. Limits are
per-IP.