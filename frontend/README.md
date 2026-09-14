# AI Vendor Outreach — Frontend

Next.js 15 (App Router) + TypeScript + Tailwind CSS v4 dashboard for the FastAPI
backend at `http://127.0.0.1:8000`.

```bash
npm install       # 46 packages
npm run build     # exits 0, emits .next/
npm start         # serve the production build
```

`NEXT_PUBLIC_API_URL` overrides the API base (default `http://127.0.0.1:8000`).

## HTTP rules (lib/api.ts)

* Base URL from `NEXT_PUBLIC_API_URL`, default `http://127.0.0.1:8000`.
* Every call uses `credentials: "include"` — the HttpOnly session cookie is owned
  by the browser; **no token is ever stored by the frontend**.
* Every POST/PUT/PATCH/DELETE adds `X-Requested-With: XMLHttpRequest`
  (backend returns 403 without it).
* Errors surface `detail` from the JSON body (including FastAPI 422 lists);
  401 redirects to `/login`.

## Auth

`lib/auth.ts` exports `requireAuth()` (server components) — it forwards the incoming
`Cookie` header to `GET /api/auth/me`, redirects to `/setup` while
`GET /api/setup/status` reports `setup_required`, and redirects to `/login` when not
authenticated. If the backend is unreachable from the Next server the page still
renders and the client-side 401 handler bounces to `/login`.

## Pages

| Route | Purpose |
| --- | --- |
| `/login` | Sign-in form; auto-forwards to `/setup` when setup is required |
| `/setup` | 3-step first-run wizard → `POST /api/setup/complete` |
| `/dashboard` | Metric cards, queue snapshot, pure-CSS bars, recent campaigns/activities |
| `/vendors` | Search + status filter, add/edit modal, research, status change, delete |
| `/vendors/find` | Discovery (`POST /api/vendors/discover?limit=N`) + paste import |
| `/campaigns` | List + create modal (`initial_email_subject` / `initial_email_body`, schedule, vendor picker) |
| `/campaigns/[id]` | Detail, activate/pause/resume/archive/complete, vendors, add vendors, pending jobs |
| `/conversations` | Searchable conversation list |
| `/conversations/[id]` | Bubble thread, send message, mark interest / qualified / meeting link, AI actions, notes |
| `/queue` | Stat cards, global pause toggle, job table with pause/resume/retry/reschedule/cancel |
| `/meetings` | Meeting table with send-invitation / mark-scheduled / complete / cancel |
| `/notifications` | Inbox with unread badge, unread filter, mark read, mark all, clear |
| `/analytics` | Overall + per-campaign cards, funnel and engagement bars, campaign table |
| `/settings` | Schema-driven section tabs, per-type forms, `PUT /api/settings/{section}` with `{section, values}`, Gmail/Telegram status + test, toasts |

Shared pieces: `components/AppShell.tsx` (dark slate/indigo sidebar with the 10 nav
items + Logout, collapsible on mobile, unread badge polling), `components/ui.tsx`
(cards, stat cards, tables, modals, badges, pure-CSS bars), `components/Toast.tsx`.

## Unwired endpoints

Every endpoint in the task contract is wired. Four backend paths in `openapi.json`
are intentionally not called from the UI:

| Endpoint | Why |
| --- | --- |
| `GET /api/health/full` | Not part of the requested UI; `GET /api/health` exists in `lib/api.ts` |
| `GET /api/integrations/gmail/callback` | OAuth landing handled by the backend; the UI redirects to `auth-url` with `redirect_uri=<origin>/settings` |
| `POST /api/queue/purge` | Destructive maintenance endpoint, not in the contract |
| `POST /api/vendors/import/csv` | Contract only asks for the paste import; CSV upload UI not built |

Note (contract vs. schema): `POST /api/notifications/read` is documented as `{"id": ...}`
in prose but `openapi.json` declares `NotificationReadPatch {ids: [...], all: bool}`.
`lib/api.ts` sends `{ id, ids: [id] }` so either contract reading works.
