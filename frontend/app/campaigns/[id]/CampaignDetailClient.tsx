"use client";

import Link from "next/link";
import { useState } from "react";

import { useToast } from "@/components/Toast";
import {
  Card,
  EmptyState,
  ErrorNote,
  Field,
  KeyValues,
  Modal,
  PageHeader,
  Spinner,
  StatCard,
  StatusBadge,
  TableShell,
} from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { CAMPAIGN_ACTIONS } from "@/lib/constants";
import { fmtDate, fmtNumber, pct } from "@/lib/format";
import { useApi } from "@/lib/useApi";

export function CampaignDetailClient({ id }: { id: string }) {
  const toast = useToast();
  const [busy, setBusy] = useState<string | null>(null);
  const [addOpen, setAddOpen] = useState(false);
  const [selected, setSelected] = useState<string[]>([]);
  const [vendorFilter, setVendorFilter] = useState("");

  const campaign = useApi(() => api.campaigns.get(id), [id]);
  const vendors = useApi(() => api.campaigns.vendors(id, { limit: 100 }), [id]);
  const pending = useApi(
    () => api.queue.list({ campaign_id: id, status: "PENDING", limit: 25 }),
    [id],
  );
  const allVendors = useApi(() => api.vendors.list({ limit: 200, offset: 0 }), []);

  const data = campaign.data ?? {};
  const metrics = data.metrics ?? {};
  const vendorItems: any[] = vendors.data?.items ?? [];
  const pendingItems: any[] = pending.data?.items ?? [];
  const candidates: any[] = (allVendors.data?.items ?? []).filter((vendor: any) => {
    if (vendorItems.some((existing) => existing.id === vendor.id)) return false;
    if (!vendorFilter) return true;
    return `${vendor.company} ${vendor.email ?? ""}`.toLowerCase().includes(vendorFilter.toLowerCase());
  });

  const act = async (action: string) => {
    if (action === "archive" && !window.confirm("Archive this campaign?")) return;
    setBusy(action);
    try {
      await api.campaigns.state(id, action as any);
      toast(`Campaign ${action}d`.replace("ee", "e"), "success");
      campaign.reload();
      pending.reload();
    } catch (err) {
      toast(errorMessage(err), "error");
    } finally {
      setBusy(null);
    }
  };

  const addVendors = async () => {
    if (selected.length === 0) {
      toast("Select at least one vendor.", "error");
      return;
    }
    setBusy("add");
    try {
      await api.campaigns.addVendors(id, selected);
      toast(`${selected.length} vendor(s) added`, "success");
      setSelected([]);
      setAddOpen(false);
      vendors.reload();
      campaign.reload();
    } catch (err) {
      toast(errorMessage(err), "error");
    } finally {
      setBusy(null);
    }
  };

  if (campaign.loading && !campaign.data) return <Spinner label="Loading campaign…" />;

  if (campaign.error && !campaign.data) {
    return (
      <div>
        <PageHeader title="Campaign" actions={<Link className="btn btn-sm" href="/campaigns">Back</Link>} />
        <ErrorNote message={campaign.error} />
      </div>
    );
  }

  return (
    <div>
      <PageHeader
        title={data.name || "Campaign"}
        subtitle={data.description || data.initial_email_subject || ""}
        actions={
          <>
            <Link className="btn btn-sm" href="/campaigns">
              Back
            </Link>
            <StatusBadge status={data.status} />
          </>
        }
      />

      <ErrorNote message={campaign.error} />

      <Card
        title="Campaign state"
        actions={
          <div className="flex flex-wrap gap-1">
            {CAMPAIGN_ACTIONS.map((action) => (
              <button
                key={action}
                type="button"
                className={`btn btn-sm ${action === "activate" ? "btn-primary" : ""}`}
                onClick={() => act(action)}
                disabled={busy !== null}
              >
                {busy === action ? "…" : action}
              </button>
            ))}
          </div>
        }
      >
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <StatCard label="Vendors" value={fmtNumber(data.vendor_count ?? vendorItems.length)} />
          <StatCard label="Batch size" value={fmtNumber(data.batch_size ?? 0)} />
          <StatCard label="Daily max" value={fmtNumber(data.daily_max ?? 0)} />
          <StatCard label="Pending jobs" value={fmtNumber(pendingItems.length)} tone="amber" />
        </div>
        <div className="mt-3">
          <p className="muted mb-1 text-xs">
            Pending share of vendor list:{" "}
            <span className="mono text-slate-300">
              {pct(pendingItems.length, Math.max(vendorItems.length, 1)).toFixed(1)}%
            </span>
          </p>
          <div className="bar-track">
            <div
              className="bar-fill"
              style={{ width: `${pct(pendingItems.length, Math.max(vendorItems.length, 1))}%`, backgroundColor: "#f59e0b" }}
            />
          </div>
        </div>
      </Card>

      <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card title="Sending window">
          <KeyValues
            data={{
              timezone: data.timezone,
              sending_start_time: data.sending_start_time,
              sending_end_time: data.sending_end_time,
              sending_days:
                Array.isArray(data.sending_days) && data.sending_days.length
                  ? data.sending_days.join(", ")
                  : data.sending_days,
              min_delay_minutes: data.min_delay_minutes,
              max_delay_minutes: data.max_delay_minutes,
              created_at: data.created_at ? fmtDate(data.created_at) : undefined,
            }}
          />
        </Card>
        <Card title="Message">
          <p className="label">Subject</p>
          <p className="mb-3 text-sm text-slate-200">{data.initial_email_subject || "—"}</p>
          <p className="label">Body</p>
          <pre className="mono max-h-56 overflow-auto whitespace-pre-wrap rounded-md border border-slate-800 bg-slate-900/50 p-3 text-slate-200">
            {data.initial_email_body || "—"}
          </pre>
        </Card>
      </div>

      {Object.keys(metrics).length > 0 ? (
        <div className="mt-4">
          <Card title="Campaign metrics">
            <KeyValues data={metrics} />
          </Card>
        </div>
      ) : null}

      <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card
          title={`Vendors (${fmtNumber(vendors.data?.total ?? vendorItems.length)})`}
          actions={
            <button type="button" className="btn btn-sm btn-primary" onClick={() => setAddOpen(true)}>
              Add vendors
            </button>
          }
        >
          <ErrorNote message={vendors.error} />
          {vendors.loading && !vendors.data ? <Spinner /> : null}
          {vendors.data && vendorItems.length === 0 ? (
            <EmptyState message="No vendors in this campaign yet." />
          ) : null}
          {vendorItems.length > 0 ? (
            <TableShell>
              <thead>
                <tr>
                  <th>Company</th>
                  <th>Email</th>
                  <th>Status</th>
                  <th>Campaign status</th>
                </tr>
              </thead>
              <tbody>
                {vendorItems.slice(0, 50).map((vendor) => (
                  <tr key={vendor.id}>
                    <td className="text-slate-100">{vendor.company}</td>
                    <td className="mono">{vendor.email || "—"}</td>
                    <td>
                      <StatusBadge status={vendor.status} />
                    </td>
                    <td>
                      <StatusBadge status={vendor.campaign_status || "—"} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </TableShell>
          ) : null}
        </Card>

        <Card
          title={`Pending jobs (${fmtNumber(pending.data?.total ?? pendingItems.length)})`}
          actions={
            <Link className="btn btn-sm" href="/queue">
              Queue
            </Link>
          }
        >
          <ErrorNote message={pending.error} />
          {pending.loading && !pending.data ? <Spinner /> : null}
          {pending.data && pendingItems.length === 0 ? (
            <EmptyState message="No pending jobs for this campaign." />
          ) : null}
          {pendingItems.length > 0 ? (
            <TableShell>
              <thead>
                <tr>
                  <th>Type</th>
                  <th>Status</th>
                  <th>Run after</th>
                  <th>Attempts</th>
                </tr>
              </thead>
              <tbody>
                {pendingItems.slice(0, 25).map((job) => (
                  <tr key={job.id}>
                    <td className="mono">{job.job_type}</td>
                    <td>
                      <StatusBadge status={job.status} />
                    </td>
                    <td className="muted text-xs">{fmtDate(job.run_after || job.scheduled_for)}</td>
                    <td className="mono">
                      {fmtNumber(job.attempts ?? job.attempt_count ?? 0)}
                      {job.max_attempts ? `/${job.max_attempts}` : ""}
                    </td>
                  </tr>
                ))}
              </tbody>
            </TableShell>
          ) : null}
        </Card>
      </div>

      <Modal
        title="Add vendors to campaign"
        open={addOpen}
        onClose={() => setAddOpen(false)}
        footer={
          <>
            <button type="button" className="btn" onClick={() => setAddOpen(false)}>
              Cancel
            </button>
            <button type="button" className="btn btn-primary" onClick={addVendors} disabled={busy === "add"}>
              {busy === "add" ? "Adding…" : `Add ${selected.length || ""}`.trim()}
            </button>
          </>
        }
      >
        <Field label="Filter">
          <input
            className="input"
            value={vendorFilter}
            onChange={(event) => setVendorFilter(event.target.value)}
            placeholder="Company or email"
          />
        </Field>
        <div className="max-h-64 overflow-y-auto rounded-md border border-slate-800 bg-slate-900/40 p-2">
          {allVendors.loading && !allVendors.data ? <Spinner label="Loading vendors…" /> : null}
          {allVendors.data && candidates.length === 0 ? (
            <p className="muted text-xs">No vendors available to add.</p>
          ) : null}
          {candidates.slice(0, 200).map((vendor) => (
            <label key={vendor.id} className="flex items-center gap-2 py-1 text-sm">
              <input
                type="checkbox"
                checked={selected.includes(vendor.id)}
                onChange={() =>
                  setSelected((current) =>
                    current.includes(vendor.id)
                      ? current.filter((value) => value !== vendor.id)
                      : [...current, vendor.id],
                  )
                }
              />
              <span className="text-slate-200">{vendor.company}</span>
              <span className="mono ml-auto text-xs text-slate-500">{vendor.status}</span>
            </label>
          ))}
        </div>
      </Modal>
    </div>
  );
}

export default CampaignDetailClient;
