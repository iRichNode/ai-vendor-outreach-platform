"use client";

import { useState } from "react";

import { useToast } from "@/components/Toast";
import {
  Card,
  EmptyState,
  ErrorNote,
  PageHeader,
  Spinner,
  StatCard,
  StatusBadge,
} from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { fmtDate, fmtNumber, humanize, truncate } from "@/lib/format";
import { useApi } from "@/lib/useApi";

const PAGE_SIZE = 30;

export function NotificationsClient() {
  const toast = useToast();
  const [unreadOnly, setUnreadOnly] = useState(false);
  const [offset, setOffset] = useState(0);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [clearing, setClearing] = useState(false);

  const notifications = useApi(
    () => api.notifications.list({ unread_only: unreadOnly, limit: PAGE_SIZE, offset }),
    [unreadOnly, offset],
  );
  const unread = useApi(() => api.notifications.unreadCount(), []);

  const items: any[] = notifications.data?.items ?? [];
  const total = Number(notifications.data?.total ?? items.length);
  const unreadCount = Number(unread.data?.unread ?? 0);
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const refresh = () => {
    notifications.reload();
    unread.reload();
  };

  const markRead = async (item: any) => {
    setBusyId(item.id);
    try {
      await api.notifications.read(item.id);
      refresh();
    } catch (err) {
      toast(errorMessage(err), "error");
    } finally {
      setBusyId(null);
    }
  };

  const markAllRead = async () => {
    setBusyId("all");
    try {
      await api.notifications.readAll();
      toast("All notifications marked read", "success");
      refresh();
    } catch (err) {
      toast(errorMessage(err), "error");
    } finally {
      setBusyId(null);
    }
  };

  const clearAll = async () => {
    if (!window.confirm("Delete all notifications?")) return;
    setClearing(true);
    try {
      await api.notifications.clear();
      toast("Notifications cleared", "success");
      refresh();
    } catch (err) {
      toast(errorMessage(err), "error");
    } finally {
      setClearing(false);
    }
  };

  return (
    <div>
      <PageHeader
        title="Notifications"
        subtitle="System events, replies and escalations"
        actions={
          <>
            <button
              type="button"
              className="btn btn-sm"
              onClick={markAllRead}
              disabled={busyId === "all" || unreadCount === 0}
            >
              Mark all read
            </button>
            <button type="button" className="btn btn-sm btn-danger" onClick={clearAll} disabled={clearing}>
              {clearing ? "Clearing…" : "Clear all"}
            </button>
          </>
        }
      />

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        <StatCard label="Unread" value={fmtNumber(unreadCount)} tone={unreadCount ? "amber" : "green"} />
        <StatCard label="Matching filter" value={fmtNumber(total)} />
        <StatCard
          label="Showing"
          value={fmtNumber(items.length)}
          hint={unreadOnly ? "Unread only" : "All notifications"}
        />
      </div>

      <div className="mt-4">
        <Card
          title="Inbox"
          actions={
            <label className="flex items-center gap-2 text-xs text-slate-300">
              <input
                type="checkbox"
                checked={unreadOnly}
                onChange={(event) => {
                  setUnreadOnly(event.target.checked);
                  setOffset(0);
                }}
              />
              Unread only
            </label>
          }
        >
          <ErrorNote message={notifications.error} />
          {notifications.loading && !notifications.data ? <Spinner label="Loading notifications…" /> : null}
          {notifications.data && items.length === 0 ? (
            <EmptyState message="No notifications." hint="Events will show up here." />
          ) : null}

          <ul className="divide-y divide-slate-800">
            {items.map((item) => (
              <li key={item.id} className="flex items-start gap-3 py-3">
                <span
                  className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${
                    item.read ? "bg-slate-600" : "bg-indigo-400"
                  }`}
                />
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className={item.read ? "text-sm text-slate-300" : "text-sm font-semibold text-slate-100"}>
                      {item.title || humanize(item.notification_type)}
                    </span>
                    <StatusBadge status={item.notification_type} />
                    {item.severity ? <span className="badge badge-slate">{item.severity}</span> : null}
                  </div>
                  <p className="muted mt-1 text-sm">{truncate(item.body, 220)}</p>
                  <p className="muted mt-1 text-xs">
                    {fmtDate(item.event_time || item.created_at)}
                    {item.link ? (
                      <>
                        {" • "}
                        <a className="text-indigo-300 hover:underline" href={item.link}>
                          open
                        </a>
                      </>
                    ) : null}
                  </p>
                </div>
                {!item.read ? (
                  <button
                    type="button"
                    className="btn btn-sm"
                    onClick={() => markRead(item)}
                    disabled={busyId === item.id}
                  >
                    {busyId === item.id ? "…" : "Mark read"}
                  </button>
                ) : (
                  <span className="muted text-xs">read</span>
                )}
              </li>
            ))}
          </ul>

          <div className="mt-4 flex items-center justify-between text-xs">
            <span className="muted">
              Page {Math.floor(offset / PAGE_SIZE) + 1} of {pages}
            </span>
            <div className="flex gap-2">
              <button
                type="button"
                className="btn btn-sm"
                disabled={offset === 0}
                onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
              >
                Previous
              </button>
              <button
                type="button"
                className="btn btn-sm"
                disabled={offset + PAGE_SIZE >= total}
                onClick={() => setOffset(offset + PAGE_SIZE)}
              >
                Next
              </button>
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
}

export default NotificationsClient;
