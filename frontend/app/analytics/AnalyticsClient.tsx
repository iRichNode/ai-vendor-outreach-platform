"use client";

import { useState } from "react";

import {
  Bar,
  Card,
  EmptyState,
  ErrorNote,
  PageHeader,
  Spinner,
  StatCard,
  StatusBadge,
  TableShell,
} from "@/components/ui";
import { api } from "@/lib/api";
import { fmtNumber, fmtPercent, humanize, pct, truncate } from "@/lib/format";
import { useApi } from "@/lib/useApi";

type Tone = "indigo" | "green" | "amber" | "red" | "slate";

const SUMMARY_CARDS: { key: string; label: string; tone: Tone; percent?: boolean }[] = [
  { key: "emails_sent", label: "Emails sent", tone: "indigo" },
  { key: "replies", label: "Replies", tone: "green" },
  { key: "reply_rate", label: "Reply rate", tone: "amber", percent: true },
  { key: "interested", label: "Interested", tone: "indigo" },
  { key: "qualified", label: "Qualified", tone: "green" },
  { key: "meetings_requested", label: "Meetings requested", tone: "indigo" },
  { key: "meetings_scheduled", label: "Meetings scheduled", tone: "green" },
  { key: "opted_out", label: "Opted out", tone: "red" },
  { key: "bounced", label: "Bounced", tone: "red" },
];

const FUNNEL_COLORS: Record<string, string> = {
  total_vendors: "#6366f1",
  in_funnel: "#818cf8",
  qualified: "#22c55e",
  meeting_requested: "#0ea5e9",
  meetings_scheduled: "#14b8a6",
  waiting_for_human: "#f59e0b",
  opted_out: "#ef4444",
  bounced: "#dc2626",
};

function num(value: unknown): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

export function AnalyticsClient() {
  const [selected, setSelected] = useState<string>("");

  const dashboard = useApi(() => api.analytics.dashboard(), []);
  const summary = useApi(() => api.analytics.summary(), []);
  const funnel = useApi(() => api.analytics.funnel(), []);

  const metrics: Record<string, unknown> = dashboard.data ?? {};
  const overall: Record<string, unknown> = summary.data?.overall ?? {};
  const campaigns: any[] = Array.isArray(summary.data?.campaigns) ? summary.data.campaigns : [];
  const series: any[] = Array.isArray(funnel.data?.series) ? funnel.data.series : [];

  const selectedSummary = campaigns.find((campaign) => campaign.campaign_id === selected) ?? null;
  const activeSummary: Record<string, unknown> = selectedSummary ?? overall;

  const funnelMax = series.reduce((max, item) => Math.max(max, num(item.value)), 0);
  const replyRate = num(activeSummary.reply_rate) * 100;
  const sentTotal = num(activeSummary.emails_sent);
  const repliedTotal = num(activeSummary.replies);

  return (
    <div>
      <PageHeader
        title="Analytics"
        subtitle="Funnel and campaign performance, computed from live data"
        actions={
          <select
            className="select w-56"
            value={selected}
            onChange={(event) => setSelected(event.target.value)}
            aria-label="Scope analytics"
          >
            <option value="">All campaigns (overall)</option>
            {campaigns.map((campaign) => (
              <option key={campaign.campaign_id} value={campaign.campaign_id}>
                {campaign.campaign_name || campaign.campaign_id}
              </option>
            ))}
          </select>
        }
      />

      <ErrorNote message={summary.error ?? dashboard.error} />

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-5">
        {SUMMARY_CARDS.map(({ key, label, tone, percent }) => (
          <StatCard
            key={key}
            label={label}
            tone={tone}
            value={
              summary.loading && !summary.data
                ? "…"
                : percent
                  ? fmtPercent(num(activeSummary[key]) * 100)
                  : fmtNumber(activeSummary[key] ?? 0)
            }
            hint={selectedSummary ? selectedSummary.campaign_name : "All campaigns"}
          />
        ))}
      </div>

      <div className="mt-4 grid grid-cols-1 gap-3 lg:grid-cols-2">
        <Card title="Funnel">
          {funnel.loading && !funnel.data ? <Spinner label="Loading funnel…" /> : null}
          {funnel.data && series.length === 0 ? (
            <EmptyState message="No vendor data yet." hint="Add or discover vendors to populate the funnel." />
          ) : null}
          <div className="space-y-3">
            {series.map((item) => (
              <Bar
                key={item.key}
                label={item.label || humanize(item.key)}
                value={num(item.value)}
                total={funnelMax}
                color={FUNNEL_COLORS[item.key] || "#6366f1"}
              />
            ))}
          </div>
        </Card>

        <Card title="Engagement">
          <div className="space-y-4">
            <Bar
              label={`Emails sent (${fmtNumber(sentTotal)})`}
              value={sentTotal}
              total={Math.max(sentTotal, 1)}
              color="#6366f1"
            />
            <Bar
              label={`Replies (${fmtNumber(repliedTotal)})`}
              value={repliedTotal}
              total={Math.max(sentTotal, 1)}
              color="#22c55e"
            />
            <Bar
              label={`Reply rate ${fmtPercent(replyRate)}`}
              value={repliedTotal}
              total={Math.max(sentTotal, 1)}
              color="#f59e0b"
            />
            <Bar
              label={`Interested / in funnel (${fmtNumber(activeSummary.interested ?? 0)} / ${fmtNumber(
                metrics.in_funnel ?? 0,
              )})`}
              value={num(activeSummary.interested)}
              total={Math.max(num(metrics.in_funnel), num(activeSummary.interested), 1)}
              color="#0ea5e9"
            />
            <Bar
              label={`Qualified (${fmtNumber(activeSummary.qualified ?? 0)})`}
              value={num(activeSummary.qualified)}
              total={Math.max(num(metrics.total_vendors), num(activeSummary.qualified), 1)}
              color="#14b8a6"
            />
          </div>
          <dl className="mt-4 grid grid-cols-2 gap-3 text-xs">
            <div>
              <dt className="muted">Total vendors</dt>
              <dd className="stat-value text-base">{fmtNumber(metrics.total_vendors ?? 0)}</dd>
            </div>
            <div>
              <dt className="muted">Active campaigns</dt>
              <dd className="stat-value text-base">{fmtNumber(metrics.active_campaigns ?? 0)}</dd>
            </div>
          </dl>
        </Card>
      </div>

      <div className="mt-4">
        <Card title="Per campaign">
          <ErrorNote message={dashboard.error} />
          {summary.loading && !summary.data ? <Spinner label="Loading campaigns…" /> : null}
          {summary.data && campaigns.length === 0 ? (
            <EmptyState message="No campaigns yet." hint="Create a campaign to see per-campaign analytics." />
          ) : null}

          {campaigns.length > 0 ? (
            <TableShell>
              <thead>
                <tr>
                  <th>Campaign</th>
                  <th>Status</th>
                  <th>Sent</th>
                  <th>Replies</th>
                  <th>Reply rate</th>
                  <th>Interested</th>
                  <th>Qualified</th>
                  <th>Meetings</th>
                  <th className="w-40">Reply volume</th>
                </tr>
              </thead>
              <tbody>
                {campaigns.map((campaign) => {
                  const sent = num(campaign.emails_sent);
                  const replied = num(campaign.replies);
                  return (
                    <tr key={campaign.campaign_id}>
                      <td className="text-slate-100">
                        <button
                          type="button"
                          className="text-left hover:text-indigo-300"
                          onClick={() => setSelected(campaign.campaign_id)}
                        >
                          {truncate(campaign.campaign_name || campaign.campaign_id, 40)}
                        </button>
                      </td>
                      <td>
                        <StatusBadge status={campaign.campaign_status} />
                      </td>
                      <td className="mono">{fmtNumber(sent)}</td>
                      <td className="mono">{fmtNumber(replied)}</td>
                      <td className="mono">{fmtPercent(num(campaign.reply_rate) * 100)}</td>
                      <td className="mono">{fmtNumber(campaign.interested)}</td>
                      <td className="mono">{fmtNumber(campaign.qualified)}</td>
                      <td className="mono">
                        {fmtNumber(campaign.meetings_scheduled)} / {fmtNumber(campaign.meetings_requested)}
                      </td>
                      <td>
                        <div className="flex items-center gap-2">
                          <div className="bar-track" style={{ width: "6rem" }}>
                            <div
                              className="bar-fill"
                              style={{ width: `${pct(replied, Math.max(sent, 1))}%`, backgroundColor: "#22c55e" }}
                            />
                          </div>
                          <span className="mono text-xs text-slate-400">
                            {fmtPercent(pct(replied, Math.max(sent, 1)))}
                          </span>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </TableShell>
          ) : null}
        </Card>
      </div>
    </div>
  );
}

export default AnalyticsClient;
