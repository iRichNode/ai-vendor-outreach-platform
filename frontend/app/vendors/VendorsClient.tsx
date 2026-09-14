"use client";

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
import { VENDOR_SOURCES, VENDOR_STATUSES } from "@/lib/constants";
import { fmtDate, fmtNumber, truncate } from "@/lib/format";
import { useApi } from "@/lib/useApi";

const PAGE_SIZE = 25;

interface VendorForm {
  company: string;
  email: string;
  contact_name: string;
  trade: string;
  city: string;
  website: string;
  source: string;
  notes: string;
}

const EMPTY_FORM: VendorForm = {
  company: "",
  email: "",
  contact_name: "",
  trade: "",
  city: "",
  website: "",
  source: "MANUAL",
  notes: "",
};

export function VendorsClient() {
  const toast = useToast();
  const [search, setSearch] = useState("");
  const [searchTerm, setSearchTerm] = useState("");
  const [status, setStatus] = useState("");
  const [offset, setOffset] = useState(0);
  const [busyId, setBusyId] = useState<string | null>(null);

  const [modalOpen, setModalOpen] = useState(false);
  const [editId, setEditId] = useState<string | null>(null);
  const [form, setForm] = useState<VendorForm>(EMPTY_FORM);
  const [saving, setSaving] = useState(false);

  const vendors = useApi(
    () =>
      api.vendors.list({
        search: searchTerm || undefined,
        status: status || undefined,
        limit: PAGE_SIZE,
        offset,
      }),
    [searchTerm, status, offset],
  );

  const items: any[] = vendors.data?.items ?? [];
  const total = Number(vendors.data?.total ?? items.length);

  const openCreate = () => {
    setEditId(null);
    setForm(EMPTY_FORM);
    setModalOpen(true);
  };

  const openEdit = (vendor: any) => {
    setEditId(vendor.id);
    setForm({
      company: vendor.company ?? "",
      email: vendor.email ?? "",
      contact_name: vendor.contact_name ?? "",
      trade: vendor.trade ?? "",
      city: vendor.city ?? "",
      website: vendor.website ?? "",
      source: vendor.source ?? "MANUAL",
      notes: vendor.notes ?? "",
    });
    setModalOpen(true);
  };

  const save = async () => {
    if (!form.company.trim()) {
      toast("Company is required.", "error");
      return;
    }
    setSaving(true);
    const payload = {
      company: form.company.trim(),
      email: form.email.trim() || null,
      contact_name: form.contact_name.trim() || null,
      trade: form.trade.trim() || null,
      city: form.city.trim() || null,
      website: form.website.trim() || null,
      notes: form.notes.trim() || null,
    };
    try {
      if (editId) {
        await api.vendors.update(editId, payload);
        toast("Vendor updated", "success");
      } else {
        await api.vendors.create({ ...payload, source: form.source || "MANUAL" });
        toast("Vendor created", "success");
      }
      setModalOpen(false);
      vendors.reload();
    } catch (err) {
      toast(errorMessage(err), "error");
    } finally {
      setSaving(false);
    }
  };

  const runResearch = async (vendor: any) => {
    setBusyId(vendor.id);
    try {
      await api.vendors.research(vendor.id);
      toast(`Research started for ${vendor.company}`, "success");
      vendors.reload();
    } catch (err) {
      toast(errorMessage(err), "error");
    } finally {
      setBusyId(null);
    }
  };

  const changeStatus = async (vendor: any, next: string) => {
    setBusyId(vendor.id);
    try {
      await api.vendors.setStatus(vendor.id, next);
      toast(`${vendor.company} → ${next}`, "success");
      vendors.reload();
    } catch (err) {
      toast(errorMessage(err), "error");
    } finally {
      setBusyId(null);
    }
  };

  const remove = async (vendor: any) => {
    if (!window.confirm(`Delete ${vendor.company}? This cannot be undone.`)) return;
    setBusyId(vendor.id);
    try {
      await api.vendors.remove(vendor.id);
      toast("Vendor deleted", "success");
      vendors.reload();
    } catch (err) {
      toast(errorMessage(err), "error");
    } finally {
      setBusyId(null);
    }
  };

  const page = Math.floor(offset / PAGE_SIZE) + 1;
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div>
      <PageHeader
        title="Vendors"
        subtitle={`${fmtNumber(total)} vendor${total === 1 ? "" : "s"} in the database`}
        actions={
          <>
            <a className="btn btn-sm" href="/vendors/find">
              Find vendors
            </a>
            <button type="button" className="btn btn-sm btn-primary" onClick={openCreate}>
              Add vendor
            </button>
          </>
        }
      />

      <Card>
        <form
          className="mb-4 flex flex-wrap items-end gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            setOffset(0);
            setSearchTerm(search.trim());
          }}
        >
          <div className="min-w-[14rem] flex-1">
            <span className="label">Search</span>
            <input
              className="input"
              placeholder="Company, contact or email"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
          </div>
          <div className="w-48">
            <span className="label">Status</span>
            <select
              className="select"
              value={status}
              onChange={(event) => {
                setStatus(event.target.value);
                setOffset(0);
              }}
            >
              <option value="">All statuses</option>
              {VENDOR_STATUSES.map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </div>
          <button className="btn btn-sm btn-primary" type="submit">
            Search
          </button>
          <button
            className="btn btn-sm"
            type="button"
            onClick={() => {
              setSearch("");
              setSearchTerm("");
              setStatus("");
              setOffset(0);
            }}
          >
            Reset
          </button>
        </form>

        <ErrorNote message={vendors.error} />
        {vendors.loading && !vendors.data ? <Spinner label="Loading vendors…" /> : null}

        {vendors.data && items.length === 0 ? (
          <EmptyState message="No vendors found." hint="Add one manually or import a list." />
        ) : null}

        {items.length > 0 ? (
          <TableShell>
            <thead>
              <tr>
                <th>Company</th>
                <th>Contact</th>
                <th>Email</th>
                <th>Trade</th>
                <th>City</th>
                <th>Status</th>
                <th>Created</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {items.map((vendor) => (
                <tr key={vendor.id}>
                  <td>
                    <span className="font-medium text-slate-100">{vendor.company}</span>
                    {vendor.website ? (
                      <a
                        className="mono block text-xs text-indigo-300 hover:underline"
                        href={vendor.website}
                        target="_blank"
                        rel="noreferrer"
                      >
                        {truncate(vendor.website, 34)}
                      </a>
                    ) : null}
                  </td>
                  <td>{vendor.contact_name || "—"}</td>
                  <td className="mono">{vendor.email || "—"}</td>
                  <td>{vendor.trade || "—"}</td>
                  <td>{vendor.city || "—"}</td>
                  <td>
                    <StatusBadge status={vendor.status} />
                    {vendor.opted_out ? <span className="badge badge-red ml-1">opt-out</span> : null}
                  </td>
                  <td className="muted text-xs">{fmtDate(vendor.created_at)}</td>
                  <td>
                    <div className="flex flex-wrap items-center gap-1">
                      <button
                        type="button"
                        className="btn btn-sm"
                        onClick={() => runResearch(vendor)}
                        disabled={busyId === vendor.id}
                      >
                        Research
                      </button>
                      <select
                        className="select w-36 !py-1 text-xs"
                        value=""
                        onChange={(event) => {
                          if (event.target.value) changeStatus(vendor, event.target.value);
                        }}
                        disabled={busyId === vendor.id}
                        aria-label={`Change status for ${vendor.company}`}
                      >
                        <option value="">Set status…</option>
                        {VENDOR_STATUSES.map((value) => (
                          <option key={value} value={value}>
                            {value}
                          </option>
                        ))}
                      </select>
                      <button type="button" className="btn btn-sm" onClick={() => openEdit(vendor)}>
                        Edit
                      </button>
                      <button
                        type="button"
                        className="btn btn-sm btn-danger"
                        onClick={() => remove(vendor)}
                        disabled={busyId === vendor.id}
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

        <div className="mt-4 flex items-center justify-between text-xs">
          <span className="muted">
            Page {page} of {pages}
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

      <Modal
        title={editId ? "Edit vendor" : "Add vendor"}
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        footer={
          <>
            <button type="button" className="btn" onClick={() => setModalOpen(false)}>
              Cancel
            </button>
            <button type="button" className="btn btn-primary" onClick={save} disabled={saving}>
              {saving ? "Saving…" : editId ? "Save changes" : "Create vendor"}
            </button>
          </>
        }
      >
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field label="Company *">
            <input
              className="input"
              value={form.company}
              onChange={(event) => setForm({ ...form, company: event.target.value })}
            />
          </Field>
          <Field label="Contact name">
            <input
              className="input"
              value={form.contact_name}
              onChange={(event) => setForm({ ...form, contact_name: event.target.value })}
            />
          </Field>
          <Field label="Email">
            <input
              className="input"
              type="email"
              value={form.email}
              onChange={(event) => setForm({ ...form, email: event.target.value })}
            />
          </Field>
          <Field label="Trade">
            <input
              className="input"
              value={form.trade}
              onChange={(event) => setForm({ ...form, trade: event.target.value })}
            />
          </Field>
          <Field label="City">
            <input
              className="input"
              value={form.city}
              onChange={(event) => setForm({ ...form, city: event.target.value })}
            />
          </Field>
          <Field label="Website">
            <input
              className="input"
              value={form.website}
              onChange={(event) => setForm({ ...form, website: event.target.value })}
              placeholder="https://"
            />
          </Field>
          {!editId ? (
            <Field label="Source">
              <select
                className="select"
                value={form.source}
                onChange={(event) => setForm({ ...form, source: event.target.value })}
              >
                {VENDOR_SOURCES.map((value) => (
                  <option key={value} value={value}>
                    {value}
                  </option>
                ))}
              </select>
            </Field>
          ) : null}
        </div>
        <Field label="Notes">
          <textarea
            className="textarea"
            value={form.notes}
            onChange={(event) => setForm({ ...form, notes: event.target.value })}
          />
        </Field>
      </Modal>
    </div>
  );
}

export default VendorsClient;
