"use client";

import { usePathname, useRouter } from "next/navigation";
import Link from "next/link";
import { useCallback, useEffect, useState, type ReactNode } from "react";

import { api } from "@/lib/api";
import { Icon, type IconName } from "./Icon";
import { ToastProvider } from "./Toast";

interface NavItem {
  href: string;
  label: string;
  icon: IconName;
}

const NAV: NavItem[] = [
  { href: "/dashboard", label: "Dashboard", icon: "dashboard" },
  { href: "/vendors", label: "Vendors", icon: "vendors" },
  { href: "/vendors/find", label: "Find Vendors", icon: "search" },
  { href: "/campaigns", label: "Campaigns", icon: "campaigns" },
  { href: "/conversations", label: "Conversations", icon: "conversations" },
  { href: "/queue", label: "Queue", icon: "queue" },
  { href: "/meetings", label: "Meetings", icon: "meetings" },
  { href: "/notifications", label: "Notifications", icon: "notifications" },
  { href: "/analytics", label: "Analytics", icon: "analytics" },
  { href: "/settings", label: "Settings", icon: "settings" },
];

function isActive(pathname: string, href: string): boolean {
  if (href === "/vendors") return pathname === "/vendors" || /^\/vendors\/[^/]+$/.test(pathname);
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function AppShell({
  user,
  children,
}: {
  user?: { username?: string; email?: string | null } | null;
  children: ReactNode;
}) {
  const pathname = usePathname() || "/dashboard";
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [unread, setUnread] = useState<number>(0);
  const [loggingOut, setLoggingOut] = useState(false);

  const loadUnread = useCallback(async () => {
    try {
      const res = await api.notifications.unreadCount();
      setUnread(Number(res?.unread ?? res?.count ?? 0) || 0);
    } catch {
      /* badge is best-effort */
    }
  }, []);

  useEffect(() => {
    loadUnread();
    const timer = setInterval(loadUnread, 30000);
    return () => clearInterval(timer);
  }, [loadUnread, pathname]);

  useEffect(() => {
    setOpen(false);
  }, [pathname]);

  const logout = async () => {
    setLoggingOut(true);
    try {
      await api.auth.logout();
    } catch {
      /* fall through to redirect */
    } finally {
      router.push("/login");
      router.refresh();
    }
  };

  const nav = (
    <nav className="flex flex-col gap-1">
      {NAV.map((item) => {
        const active = isActive(pathname, item.href);
        return (
          <Link
            key={item.href}
            href={item.href}
            className={`sidebar-link ${active ? "sidebar-link-active" : ""}`}
          >
            <Icon name={item.icon} />
            <span className="flex-1">{item.label}</span>
            {item.href === "/notifications" && unread > 0 ? (
              <span className="badge badge-red">{unread > 99 ? "99+" : unread}</span>
            ) : null}
          </Link>
        );
      })}
      <button type="button" className="sidebar-link mt-1 text-left" onClick={logout} disabled={loggingOut}>
        <Icon name="logout" />
        <span className="flex-1">{loggingOut ? "Logging out…" : "Logout"}</span>
      </button>
    </nav>
  );

  return (
    <ToastProvider>
      <div className="min-h-screen bg-[#0b1120]">
        {/* Mobile top bar */}
        <div className="sticky top-0 z-40 flex items-center justify-between border-b border-slate-800 bg-[#0b1120]/95 px-3 py-2 lg:hidden">
          <div className="flex items-center gap-2">
            <span className="grid h-7 w-7 place-items-center rounded-md bg-indigo-600 text-xs font-bold text-white">
              AV
            </span>
            <span className="text-sm font-semibold">AI Vendor Outreach</span>
          </div>
          <button
            type="button"
            className="btn btn-sm"
            onClick={() => setOpen((value) => !value)}
            aria-label={open ? "Close navigation" : "Open navigation"}
            aria-expanded={open}
          >
            <Icon name={open ? "close" : "menu"} size={18} />
          </button>
        </div>

        <div className="flex">
          {/* Sidebar */}
          <aside
            className={`${
              open ? "block" : "hidden"
            } fixed inset-x-0 top-12 z-30 max-h-[calc(100vh-3rem)] overflow-y-auto border-b border-slate-800 bg-[#0d1526] p-3 lg:sticky lg:top-0 lg:block lg:h-screen lg:w-64 lg:shrink-0 lg:border-b-0 lg:border-r lg:overflow-y-auto`}
          >
            <div className="mb-4 hidden items-center gap-2 lg:flex">
              <span className="grid h-8 w-8 place-items-center rounded-md bg-indigo-600 text-sm font-bold text-white">
                AV
              </span>
              <div>
                <p className="text-sm font-semibold leading-tight">AI Vendor Outreach</p>
                <p className="muted text-xs leading-tight">Operator console</p>
              </div>
            </div>
            {nav}
            <div className="mt-4 border-t border-slate-800 pt-3">
              <p className="muted text-xs">Signed in as</p>
              <p className="mono truncate text-slate-200">{user?.username || "unknown"}</p>
              {user?.email ? <p className="mono truncate text-slate-400">{user.email}</p> : null}
            </div>
          </aside>

          <main className="min-w-0 flex-1 px-3 py-5 sm:px-5 lg:px-8">
            {children}
          </main>
        </div>
      </div>
    </ToastProvider>
  );
}

export default AppShell;
