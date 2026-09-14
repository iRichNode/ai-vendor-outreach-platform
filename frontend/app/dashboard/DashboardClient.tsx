"use client";

import Link from "next/link";

import { Bar, Card, EmptyState, ErrorNote, PageHeader, Spinner, StatCard, StatusBadge } from "@/components/ui";
import { api } from "@/lib/api";
import { fmtDate, fmtNumber, humanize, pct } from "@/lib/format";
import { useApi } from "@/lib/useApi";

interface Activity {
  id?: string;
  type?: string;
  action?: string;
  event?: string;
  message?: string;
  description?: string;
  vendor?: string;
  company?: string;
  created_at?: string;
  timestamp?: string;
  event_time?: string;
}

function activityText(item: Activity): string {
  return (
    item.message ||
    item.description ||
    item.action ||
    item.event ||
    item.type ||
    "Activity"
  );
}

function activityWhen(item: Activity): string {
  return fmtDate(item.created_at || item.timestamp || item.event_time);
}

export function DashboardClient() {
  const dashboard = useApi(() => api.dashboard(), []);
  const queueStats = useApi(() => api.queue.stats(), []);
  const unread = useApi(() => api.notifications.unreadCount(), []);

  const metrics: Record<string, unknown> = dashboard.data?.metrics ?? {};
  const numeric = Object.entries(metrics).filter(([, value]) => typeof value === "number") as [
    string,
    number,
  ][];
  const campaigns: any[] =
    dashboard.data?.recent_campaigns ?? dashboard.data?.campaigns ?? dashboard.data?.recent ?? [];
  const activities: Activity[] =
    dashboard.data?.recent_activities ?? dashboard.data?.activities ?? [];

  const sent = Number(metrics.emails_sent ?? metrics.sent ?? 0);
  const replies = Number(metrics.replies ?? metrics.replies_received ?? 0);
  const stats = queueStats.data ?? {};

  if (dashboard.loading && !dashboard.data) return <Spinner label="Loading dashboard…" />;

  return (
    <div>
      <PageHeader
        title="Dashboard"
        subtitle="Live snapshot of outreach activity"
        actions={
          <>
            <Link className="btn btn-sm" href="/queue">
              Queue
            </Link>
            <Link className="btn btn-sm btn-primary" href="/campaigns">
              New campaign
            </Link>
          </>
        }
      />

      <ErrorNote message={dashboard.error} />

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-4">
        {numeric.length === 0 ? (
          <div className="col-span-full">
            <EmptyState message="No metrics reported yet." hint="Metrics appear once vendors and campaigns exist." />
          </div>
        ) : null}
        {numeric.map(([key, value]) => (
          <StatCard key={key} label={humanize(key)} value={fmtNumber(value)} />
        ))}
      </div>

      <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card title="Outreach funnel">
          <div className="space-y-3">
            <Bar label="Emails sent" value={sent} total={Math.max(sent, 1)} color="#6366f1" />
            <Bar
              label="Replies"
              value={replies}
              total={Math.max(sent, 1)}
              color="#10b981"
            />
            <p className="muted text-xs">
              Reply rate: <span className="mono text-slate-300">{pct(replies, sent).toFixed(1)}%</span>
            </p>
          </div>
        </Card>

        <Card title="Queue health" actions={<Link className="btn btn-sm" href="/queue">Manage</Link>}>
          {queueStats.error ? <ErrorNote message={queueStats.error} /> : null}
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            {["total", "pending", "claimed", "paused", "failed", "completed"].map((key) => (
              <div key={key} className="rounded-md border border-slate-800 bg-slate-900/40 px-3 py-2">
                <p className="muted text-xs uppercase tracking-wide">{humanize(key)}</p>
                <p className="mono text-lg text-slate-100">{fmtNumber(stats[key] ?? 0)}</p>
              </div>
            ))}
          </div>
          <p className="mt-3 text-xs">
            Global pause:{" "}
            <span className={stats.global_paused ? "badge badge-red" : "badge badge-green"}>
              {stats.global_paused ? "paused" : "running"}
            </span>
          </p>
        </Card>

        <Card title="Recent campaigns" actions={<Link className="btn btn-sm" href="/campaigns">All</Link>}>
          {campaigns.length === 0 ? (
            <EmptyState message="No campaigns yet." hint="Create one to start outreach." />
          ) : (
            <ul className="divide-y divide-slate-800">
              {campaigns.slice(0, 6).map((campaign) => (
                <li key={campaign.id} className="flex items-center justify-between gap-3 py-2">
                  <div className="min-w-0">
                    <Link className="truncate text-sm text-slate-100 hover:text-indigo-300" href={`/campaigns/${campaign.id}`}>
                      {campaign.name || "Untitled campaign"}
                    </Link>
                    <p className="muted text-xs">
                      {fmtNumber(campaign.vendor_count ?? 0)} vendors • {fmtDate(campaign.created_at)}
                    </p>
                  </div>
                  <StatusBadge status={campaign.status} />
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card
          title="Recent activity"
          actions={
            <Link className="btn btn-sm" href="/notifications">
              Inbox{unread.data?.unread ? ` (${unread.data.unread})` : ""}
            </Link>
          }
        >
          {activities.length === 0 ? (
            <EmptyState message="No recent activity." />
          ) : (
            <ul className="space-y-2">
              {activities.slice(0, 8).map((item, index) => (
                <li key={item.id || index} className="flex items-start gap-2 text-sm">
                  <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-indigo-400" />
                  <div className="min-w-0">
                    <p className="text-slate-200">{activityText(item)}</p>
                    <p className="muted text-xs">
                      {item.company ? `${item.company} • ` : ""}
                      {activityWhen(item)}
                    </p>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </div>
  );
}

export default DashboardClient;
