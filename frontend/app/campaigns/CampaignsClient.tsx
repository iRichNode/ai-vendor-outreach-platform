"use client";

import Link from "next/link";
import { useState } from "react";

import { useToast } from "@/components/Toast";
import {
  Card,
  EmptyState,
  ErrorNote,
  Field,
  Modal,
  PageHeader,
  Spinner,
  StatusBadge,
  TableShell,
} from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { CAMPAIGN_STATUSES, TIMEZONES, WEEKDAYS } from "@/lib/constants";
import { fmtDate, fmtNumber } from "@/lib/format";
import { useApi } from "@/lib/useApi";

export function CampaignsClient() {
  const toast = useToast();
  const [status, setStatus] = useState("");
  const [modalOpen, setModalOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [vendorFilter, setVendorFilter] = useState("");

  const [form, setForm] = useState({
    name: "",
    initial_email_subject: "",
    initial_email_body: "",
    timezone: "America/New_York",
    sending_start_time: "09:00",
    sending_end_time: "17:00",
    sending_days: [0, 1, 2, 3, 4] as number[],
    batch_size: 1,
    daily_max: 30,
    min_delay_minutes: 5,
    max_delay_minutes: 12,
    vendor_ids: [] as string[],
  });

  const campaigns = useApi(() => api.campaigns.list({ status: status || undefined, limit: 50 }), [status]);
  const vendors = useApi(() => api.vendors.list({ limit: 200, offset: 0 }), []);

  const items: any[] = campaigns.data?.items ?? [];
  const vendorItems: any[] = vendors.data?.items ?? [];
  const filteredVendors = vendorFilter
    ? vendorItems.filter((vendor) =>
        `${vendor.company} ${vendor.email ?? ""}`.toLowerCase().includes(vendorFilter.toLowerCase()),
      )
    : vendorItems;

  const toggleDay = (day: number) => {
    setForm((current) => ({
      ...current,
      sending_days: current.sending_days.includes(day)
        ? current.sending_days.filter((value) => value !== day)
        : [...current.sending_days, day].sort((a, b) => a - b),
    }));
  };

  const toggleVendor = (id: string) => {
    setForm((current) => ({
      ...current,
      vendor_ids: current.vendor_ids.includes(id)
        ? current.vendor_ids.filter((value) => value !== id)
        : [...current.vendor_ids, id],
    }));
  };

  const submit = async () => {
    if (!form.name.trim() || !form.initial_email_subject.trim() || !form.initial_email_body.trim()) {
      toast("Name, subject and body are required.", "error");
      return;
    }
    if (form.min_delay_minutes > form.max_delay_minutes) {
      toast("Min delay cannot exceed max delay.", "error");
      return;
    }
    setSaving(true);
    try {
      // NOTE: the API requires initial_email_subject / initial_email_body.
      await api.campaigns.create({
        name: form.name.trim(),
        initial_email_subject: form.initial_email_subject,
        initial_email_body: form.initial_email_body,
        timezone: form.timezone,
        sending_start_time: form.sending_start_time || null,
        sending_end_time: form.sending_end_time || null,
        sending_days: form.sending_days.length ? form.sending_days : null,
        batch_size: Number(form.batch_size) || 1,
        daily_max: Number(form.daily_max) || 1,
        min_delay_minutes: Number(form.min_delay_minutes) || 1,
        max_delay_minutes: Number(form.max_delay_minutes) || 1,
        vendor_ids: form.vendor_ids,
      });
      toast("Campaign created", "success");
      setModalOpen(false);
      setForm({ ...form, name: "", initial_email_subject: "", initial_email_body: "", vendor_ids: [] });
      campaigns.reload();
    } catch (err) {
      toast(errorMessage(err), "error");
    } finally {
      setSaving(false);
    }
  };

  const remove = async (campaign: any) => {
    if (!window.confirm(`Delete campaign “${campaign.name}”?`)) return;
    try {
      await api.campaigns.remove(campaign.id);
      toast("Campaign deleted", "success");
      campaigns.reload();
    } catch (err) {
      toast(errorMessage(err), "error");
    }
  };

  return (
    <div>
      <PageHeader
        title="Campaigns"
        subtitle={`${fmtNumber(campaigns.data?.total ?? items.length)} campaign(s)`}
        actions={
          <button type="button" className="btn btn-sm btn-primary" onClick={() => setModalOpen(true)}>
            New campaign
          </button>
        }
      />

      <Card>
        <div className="mb-4 flex items-end gap-2">
          <div className="w-48">
            <span className="label">Status</span>
            <select
              className="select"
              value={status}
              onChange={(event) => setStatus(event.target.value)}
            >
              <option value="">All statuses</option>
              {CAMPAIGN_STATUSES.map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </div>
        </div>

        <ErrorNote message={campaigns.error} />
        {campaigns.loading && !campaigns.data ? <Spinner label="Loading campaigns…" /> : null}
        {campaigns.data && items.length === 0 ? (
          <EmptyState message="No campaigns yet." hint="Create a campaign to queue outreach." />
        ) : null}

        {items.length > 0 ? (
          <TableShell>
            <thead>
              <tr>
                <th>Name</th>
                <th>Status</th>
                <th>Vendors</th>
                <th>Batch</th>
                <th>Daily max</th>
                <th>Timezone</th>
                <th>Created</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {items.map((campaign) => (
                <tr key={campaign.id}>
                  <td>
                    <Link className="text-slate-100 hover:text-indigo-300" href={`/campaigns/${campaign.id}`}>
                      {campaign.name}
                    </Link>
                    <p className="muted text-xs">{campaign.initial_email_subject || "—"}</p>
                  </td>
                  <td>
                    <StatusBadge status={campaign.status} />
                  </td>
                  <td className="mono">{fmtNumber(campaign.vendor_count ?? 0)}</td>
                  <td className="mono">{fmtNumber(campaign.batch_size ?? 0)}</td>
                  <td className="mono">{fmtNumber(campaign.daily_max ?? 0)}</td>
                  <td className="mono">{campaign.timezone || "—"}</td>
                  <td className="muted text-xs">{fmtDate(campaign.created_at)}</td>
                  <td>
                    <div className="flex gap-1">
                      <Link className="btn btn-sm" href={`/campaigns/${campaign.id}`}>
                        Open
                      </Link>
                      <button
                        type="button"
                        className="btn btn-sm btn-danger"
                        onClick={() => remove(campaign)}
                      >
                        Delete
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </TableShell>
        ) : null}
      </Card>

      <Modal
        title="New campaign"
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        footer={
          <>
            <button type="button" className="btn" onClick={() => setModalOpen(false)}>
              Cancel
            </button>
            <button type="button" className="btn btn-primary" onClick={submit} disabled={saving}>
              {saving ? "Creating…" : "Create campaign"}
            </button>
          </>
        }
      >
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field label="Name *">
            <input
              className="input"
              value={form.name}
              onChange={(event) => setForm({ ...form, name: event.target.value })}
            />
          </Field>
          <Field label="Timezone">
            <select
              className="select"
              value={form.timezone}
              onChange={(event) => setForm({ ...form, timezone: event.target.value })}
            >
              {TIMEZONES.map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </Field>
        </div>

        <Field label="Initial email subject *">
          <input
            className="input"
            value={form.initial_email_subject}
            onChange={(event) => setForm({ ...form, initial_email_subject: event.target.value })}
          />
        </Field>

        <Field label="Initial email body *" hint="Plain text. Supports placeholders if configured server-side.">
          <textarea
            className="textarea"
            value={form.initial_email_body}
            onChange={(event) => setForm({ ...form, initial_email_body: event.target.value })}
          />
        </Field>

        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Field label="Send start">
            <input
              className="input"
              type="time"
              value={form.sending_start_time}
              onChange={(event) => setForm({ ...form, sending_start_time: event.target.value })}
            />
          </Field>
          <Field label="Send end">
            <input
              className="input"
              type="time"
              value={form.sending_end_time}
              onChange={(event) => setForm({ ...form, sending_end_time: event.target.value })}
            />
          </Field>
          <Field label="Batch size">
            <input
              className="input"
              type="number"
              min={1}
              max={100}
              value={form.batch_size}
              onChange={(event) => setForm({ ...form, batch_size: Number(event.target.value) })}
            />
          </Field>
          <Field label="Daily max">
            <input
              className="input"
              type="number"
              min={1}
              max={1000}
              value={form.daily_max}
              onChange={(event) => setForm({ ...form, daily_max: Number(event.target.value) })}
            />
          </Field>
          <Field label="Min delay (min)">
            <input
              className="input"
              type="number"
              min={1}
              max={1440}
              value={form.min_delay_minutes}
              onChange={(event) => setForm({ ...form, min_delay_minutes: Number(event.target.value) })}
            />
          </Field>
          <Field label="Max delay (min)">
            <input
              className="input"
              type="number"
              min={1}
              max={1440}
              value={form.max_delay_minutes}
              onChange={(event) => setForm({ ...form, max_delay_minutes: Number(event.target.value) })}
            />
          </Field>
        </div>

        <div>
          <span className="label">Sending days</span>
          <div className="flex flex-wrap gap-2">
            {WEEKDAYS.map((day) => {
              const active = form.sending_days.includes(day.value);
              return (
                <button
                  key={day.value}
                  type="button"
                  className={`btn btn-sm ${active ? "btn-primary" : ""}`}
                  onClick={() => toggleDay(day.value)}
                  aria-pressed={active}
                >
                  {day.label}
                </button>
              );
            })}
          </div>
        </div>

        <div>
          <span className="label">
            Vendors ({form.vendor_ids.length} selected)
          </span>
          <input
            className="input mb-2"
            placeholder="Filter vendors…"
            value={vendorFilter}
            onChange={(event) => setVendorFilter(event.target.value)}
          />
          <div className="max-h-48 overflow-y-auto rounded-md border border-slate-800 bg-slate-900/40 p-2">
            {vendors.loading && !vendors.data ? <Spinner label="Loading vendors…" /> : null}
            {filteredVendors.length === 0 ? (
              <p className="muted text-xs">No vendors available.</p>
            ) : (
              filteredVendors.slice(0, 200).map((vendor) => (
                <label key={vendor.id} className="flex items-center gap-2 py-1 text-sm">
                  <input
                    type="checkbox"
                    checked={form.vendor_ids.includes(vendor.id)}
                    onChange={() => toggleVendor(vendor.id)}
                  />
                  <span className="text-slate-200">{vendor.company}</span>
                  <span className="mono ml-auto text-xs text-slate-500">{vendor.status}</span>
                </label>
              ))
            )}
          </div>
        </div>
      </Modal>
    </div>
  );
}

export default CampaignsClient;
