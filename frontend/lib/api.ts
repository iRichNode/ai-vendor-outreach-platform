/**
 * Single HTTP helper for the FastAPI backend.
 *
 * Rules implemented here:
 *  - Base URL comes from NEXT_PUBLIC_API_URL (default http://127.0.0.1:8000).
 *  - Every request is sent with `credentials: "include"` so the HttpOnly session
 *    cookie travels with the request. The browser owns the cookie: this app never
 *    reads, writes or stores any token/session material.
 *  - Every mutating request (POST/PUT/PATCH/DELETE) carries
 *    `X-Requested-With: XMLHttpRequest`, which the backend requires (otherwise 403).
 *  - Errors throw `ApiError` carrying the backend `detail` string when available.
 *  - 401 responses bounce the browser to /login.
 */

export const API_BASE = (
  process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000"
).replace(/\/+$/, "");

export type Json = Record<string, any>;
export type AnyRecord = Record<string, any>;

export class ApiError extends Error {
  status: number;
  detail: string;
  payload: unknown;

  constructor(status: number, detail: string, payload?: unknown) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
    this.payload = payload;
  }
}

const MUTATING_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);

export function errorMessage(err: unknown): string {
  if (err instanceof ApiError) return err.detail || `Request failed (${err.status})`;
  if (err instanceof Error) return err.message;
  return String(err);
}

function extractDetail(payload: unknown, fallback: string): string {
  if (payload === null || payload === undefined) return fallback;
  if (typeof payload === "string") return payload.trim() || fallback;
  const body = payload as AnyRecord;
  const detail = body.detail ?? body.message ?? body.error;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const parts = detail.map((entry) => {
      if (typeof entry === "string") return entry;
      const item = entry as AnyRecord;
      const loc = Array.isArray(item.loc) ? item.loc.join(".") : "";
      const msg = typeof item.msg === "string" ? item.msg : JSON.stringify(item);
      return loc ? `${loc}: ${msg}` : msg;
    });
    if (parts.length) return parts.join("; ");
  }
  if (detail && typeof detail === "object") return JSON.stringify(detail);
  try {
    const encoded = JSON.stringify(body);
    return encoded && encoded !== "{}" ? encoded : fallback;
  } catch {
    return fallback;
  }
}

export function query(params?: Record<string, unknown>): string {
  if (!params) return "";
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    search.set(key, String(value));
  }
  const encoded = search.toString();
  return encoded ? `?${encoded}` : "";
}

export interface RequestOptions {
  method?: string;
  body?: unknown;
  signal?: AbortSignal;
}

export async function apiFetch<T = any>(path: string, options: RequestOptions = {}): Promise<T> {
  const method = (options.method || "GET").toUpperCase();
  const headers: Record<string, string> = { Accept: "application/json" };

  if (options.body !== undefined && options.body !== null) {
    headers["Content-Type"] = "application/json";
  }
  // The backend rejects state-changing requests without this header (403).
  if (MUTATING_METHODS.has(method)) {
    headers["X-Requested-With"] = "XMLHttpRequest";
  }

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method,
      headers,
      credentials: "include",
      cache: "no-store",
      signal: options.signal,
      body:
        options.body === undefined || options.body === null
          ? undefined
          : JSON.stringify(options.body),
    });
  } catch (err) {
    if ((err as Error)?.name === "AbortError") throw err;
    throw new ApiError(0, `Network error: could not reach ${API_BASE}${path}`);
  }

  const raw = await response.text();
  let payload: any = null;
  if (raw) {
    try {
      payload = JSON.parse(raw);
    } catch {
      payload = raw;
    }
  }

  if (response.status === 401) {
    if (typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
      window.location.href = "/login";
    }
    throw new ApiError(401, extractDetail(payload, "Not authenticated"), payload);
  }

  if (!response.ok) {
    throw new ApiError(
      response.status,
      extractDetail(payload, `Request failed (${response.status} ${response.statusText})`),
      payload,
    );
  }

  return payload as T;
}

const get = <T = any>(path: string) => apiFetch<T>(path);
const post = <T = any>(path: string, body?: unknown) =>
  apiFetch<T>(path, { method: "POST", body });
const patch = <T = any>(path: string, body?: unknown) =>
  apiFetch<T>(path, { method: "PATCH", body });
const put = <T = any>(path: string, body?: unknown) => apiFetch<T>(path, { method: "PUT", body });
const del = <T = any>(path: string) => apiFetch<T>(path, { method: "DELETE" });

export const api = {
  /* ---------------------------------------------------------------- auth */
  auth: {
    me: () => get("/api/auth/me"),
    login: (username: string, password: string) =>
      post("/api/auth/login", { username, password }),
    logout: () => post("/api/auth/logout"),
  },

  setup: {
    status: () => get("/api/setup/status"),
    complete: (body: { username: string; password: string; email?: string | null }) =>
      post("/api/setup/complete", body),
  },

  /* ----------------------------------------------------------- dashboard */
  dashboard: () => get("/api/dashboard"),

  /* ------------------------------------------------------------- vendors */
  vendors: {
    list: (params?: { search?: string; status?: string; trade?: string; city?: string; opted_out?: boolean; limit?: number; offset?: number }) =>
      get(`/api/vendors${query(params)}`),
    meta: () => get("/api/vendors/meta"),
    get: (id: string) => get(`/api/vendors/${encodeURIComponent(id)}`),
    create: (body: AnyRecord) => post("/api/vendors", body),
    update: (id: string, body: AnyRecord) =>
      patch(`/api/vendors/${encodeURIComponent(id)}`, body),
    remove: (id: string) => del(`/api/vendors/${encodeURIComponent(id)}`),
    setStatus: (id: string, status: string) =>
      post(`/api/vendors/${encodeURIComponent(id)}/status`, { status }),
    research: (id: string) => post(`/api/vendors/${encodeURIComponent(id)}/research`),
    discover: (limit = 10) => post(`/api/vendors/discover${query({ limit })}`),
    importPaste: (body: { text: string; trade?: string; city?: string; state?: string; country?: string }) =>
      post("/api/vendors/import/paste", body),
  },

  /* ----------------------------------------------------------- campaigns */
  campaigns: {
    list: (params?: { status?: string; limit?: number; offset?: number }) =>
      get(`/api/campaigns${query(params)}`),
    get: (id: string) => get(`/api/campaigns/${encodeURIComponent(id)}`),
    create: (body: AnyRecord) => post("/api/campaigns", body),
    update: (id: string, body: AnyRecord) =>
      patch(`/api/campaigns/${encodeURIComponent(id)}`, body),
    remove: (id: string) => del(`/api/campaigns/${encodeURIComponent(id)}`),
    state: (id: string, action: "activate" | "pause" | "resume" | "archive" | "complete") =>
      post(`/api/campaigns/${encodeURIComponent(id)}/state`, { action }),
    addVendors: (id: string, vendor_ids: string[]) =>
      post(`/api/campaigns/${encodeURIComponent(id)}/vendors`, { vendor_ids }),
    vendors: (id: string, params?: { limit?: number; offset?: number }) =>
      get(`/api/campaigns/${encodeURIComponent(id)}/vendors${query(params)}`),
  },

  /* ------------------------------------------------------- conversations */
  conversations: {
    list: (params?: { status?: string; search?: string; vendor_id?: string; limit?: number; offset?: number }) =>
      get(`/api/conversations${query(params)}`),
    get: (id: string) => get(`/api/conversations/${encodeURIComponent(id)}`),
    sendMessage: (id: string, body: string, subject?: string) =>
      post(`/api/conversations/${encodeURIComponent(id)}/messages`, { body, subject }),
    action: (id: string, action: string, note?: string) =>
      post(`/api/conversations/${encodeURIComponent(id)}/action`, { action, note }),
    markInterest: (id: string, interested = true) =>
      post(`/api/conversations/${encodeURIComponent(id)}/mark-interest`, { interested }),
    markQualified: (id: string, qualified = true) =>
      post(`/api/conversations/${encodeURIComponent(id)}/mark-qualified`, { qualified }),
    meetingLink: (id: string, meeting_url: string, notes?: string) =>
      post(`/api/conversations/${encodeURIComponent(id)}/meeting-link`, { meeting_url, notes }),
    addNote: (id: string, note: string) =>
      post(`/api/conversations/${encodeURIComponent(id)}/notes`, { note }),
  },

  /* ------------------------------------------------------------- meetings */
  meetings: {
    list: (params?: { status?: string; campaign_id?: string; limit?: number; offset?: number }) =>
      get(`/api/meetings${query(params)}`),
    get: (id: string) => get(`/api/meetings/${encodeURIComponent(id)}`),
    sendInvitation: (id: string) =>
      post(`/api/meetings/${encodeURIComponent(id)}/send-invitation`),
    cancel: (id: string, reason = "") =>
      post(`/api/meetings/${encodeURIComponent(id)}/cancel`, { reason }),
    complete: (id: string) => post(`/api/meetings/${encodeURIComponent(id)}/complete`),
    markScheduled: (id: string, scheduled_time?: string | null) =>
      post(`/api/meetings/${encodeURIComponent(id)}/mark-scheduled`, {
        scheduled_time: scheduled_time || null,
      }),
  },

  /* ---------------------------------------------------------------- queue */
  queue: {
    stats: () => get("/api/queue/stats"),
    list: (params?: { status?: string; job_type?: string; campaign_id?: string; vendor_id?: string; limit?: number; offset?: number }) =>
      get(`/api/queue${query(params)}`),
    globalPauseStatus: () => get("/api/queue/global-pause"),
    setGlobalPause: (paused: boolean) => post("/api/queue/global-pause", { paused }),
    pause: (id: string) => post(`/api/queue/${encodeURIComponent(id)}/pause`),
    resume: (id: string) => post(`/api/queue/${encodeURIComponent(id)}/resume`),
    cancel: (id: string) => post(`/api/queue/${encodeURIComponent(id)}/cancel`),
    retry: (id: string) => post(`/api/queue/${encodeURIComponent(id)}/retry`),
    reschedule: (id: string, run_after: string, reason?: string) =>
      post(`/api/queue/${encodeURIComponent(id)}/reschedule`, { run_after, reason }),
  },

  /* -------------------------------------------------------- notifications */
  notifications: {
    list: (params?: { unread_only?: boolean; limit?: number; offset?: number }) =>
      get(`/api/notifications${query(params)}`),
    unreadCount: () => get("/api/notifications/unread-count"),
    // openapi.json declares NotificationReadPatch {ids: [...], all: bool}; the task contract
    // text mentions {"id"}. Send both keys — the backend ignores unknown fields.
    read: (id: string) => post("/api/notifications/read", { id, ids: [id] }),
    readAll: () => post("/api/notifications/read", { all: true }),
    clear: () => post("/api/notifications/clear"),
  },

  /* ------------------------------------------------------------ analytics */
  analytics: {
    dashboard: (campaign_id?: string) => get(`/api/analytics/dashboard${query({ campaign_id })}`),
    funnel: (campaign_id?: string) => get(`/api/analytics/funnel${query({ campaign_id })}`),
    summary: () => get("/api/analytics/summary"),
  },

  /* ------------------------------------------------------------- settings */
  settings: {
    get: () => get("/api/settings"),
    schema: () => get("/api/settings/schema"),
    updateSection: (section: string, values: AnyRecord) =>
      put(`/api/settings/${encodeURIComponent(section)}`, { section, values }),
  },

  /* --------------------------------------------------------- integrations */
  integrations: {
    gmailStatus: () => get("/api/integrations/gmail/status"),
    gmailAuthUrl: (redirect_uri?: string) =>
      get(`/api/integrations/gmail/auth-url${query({ redirect_uri })}`),
    gmailDisconnect: () => post("/api/integrations/gmail/disconnect"),
    telegramStatus: () => get("/api/integrations/telegram/status"),
    telegramTest: () => post("/api/integrations/telegram/test"),
  },

  /* -------------------------------------------------------------- health */
  health: () => get("/api/health"),
};

export default api;
