/**
 * Server-side auth guard.
 *
 * The browser holds the HttpOnly session cookie issued by the FastAPI backend.
 * Server components forward the incoming Cookie header to the backend so they can
 * verify the session before rendering (requireAuth()). No tokens are ever read or
 * stored by this frontend.
 */
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { API_BASE } from "./api";

/**
 * Absolute base for server-side fetches: Node's fetch cannot use relative
 * URLs, so SSR needs a real origin. API_INTERNAL_URL points at the backend
 * over the compose network (http://api:8000); fall back to the public base
 * when provided, and to the local dev backend as a last resort.
 */
const SSR_API_BASE =
  process.env.API_INTERNAL_URL ||
  (process.env.NEXT_PUBLIC_API_URL || "").replace(/\/+$/, "") ||
  API_BASE ||
  "http://127.0.0.1:8000";

export interface AuthUser {
  id?: string;
  username?: string;
  email?: string | null;
  [key: string]: unknown;
}

export interface MeResponse {
  authenticated: boolean;
  user: AuthUser | null;
}

export interface SetupStatus {
  setup_required?: boolean;
  demo_mode?: boolean;
}

/** Server-side GET against the API, forwarding the caller's cookies. */
export async function serverGet<T>(path: string): Promise<T | null> {
  try {
    const cookieHeader = (await cookies()).toString();
    const response = await fetch(`${SSR_API_BASE}${path}`, {
      headers: { cookie: cookieHeader, accept: "application/json" },
      cache: "no-store",
    });
    if (!response.ok) return null;
    return (await response.json()) as T;
  } catch {
    // Backend unreachable from the Next server process.
    return null;
  }
}

/**
 * Guard used by every protected page: redirects to /setup when the instance has
 * not been initialised yet, and to /login when there is no valid session.
 */
export async function requireAuth(): Promise<MeResponse> {
  const setup = await serverGet<SetupStatus>("/api/setup/status");
  if (setup?.setup_required) redirect("/setup");

  const me = await serverGet<MeResponse>("/api/auth/me");
  if (me?.authenticated) return me;

  if (me === null) {
    // Backend was not reachable from this process. Do not hard-lock the user out:
    // render the page and let the client-side 401 handler redirect to /login.
    return { authenticated: false, user: null };
  }

  redirect("/login");
}

export async function isSetupRequired(): Promise<boolean> {
  const setup = await serverGet<SetupStatus>("/api/setup/status");
  return Boolean(setup?.setup_required);
}
