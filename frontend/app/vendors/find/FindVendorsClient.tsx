"use client";

import { useState } from "react";

import { useToast } from "@/components/Toast";
import { Card, ErrorNote, Field, KeyValues, PageHeader, Spinner, TableShell } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { useApi } from "@/lib/useApi";

export function FindVendorsClient() {
  const toast = useToast();
  const [limit, setLimit] = useState(10);
  const [discovering, setDiscovering] = useState(false);
  const [discoverError, setDiscoverError] = useState<string | null>(null);
  const [discoverResult, setDiscoverResult] = useState<any>(null);

  const [text, setText] = useState("");
  const [trade, setTrade] = useState("");
  const [city, setCity] = useState("");
  const [region, setRegion] = useState("");
  const [importing, setImporting] = useState(false);
  const [importError, setImportError] = useState<string | null>(null);
  const [importResult, setImportResult] = useState<any>(null);

  const recent = useApi(() => api.vendors.list({ limit: 8, offset: 0 }), []);

  const discover = async () => {
    setDiscovering(true);
    setDiscoverError(null);
    try {
      const result = await api.vendors.discover(Number(limit) || 10);
      setDiscoverResult(result);
      toast("Discovery run complete", "success");
      recent.reload();
    } catch (err) {
      const message = errorMessage(err);
      setDiscoverError(message);
      toast(message, "error");
    } finally {
      setDiscovering(false);
    }
  };

  const importPaste = async () => {
    if (!text.trim()) {
      toast("Paste at least one line first.", "error");
      return;
    }
    setImporting(true);
    setImportError(null);
    try {
      const result = await api.vendors.importPaste({
        text,
        trade: trade.trim() || undefined,
        city: city.trim() || undefined,
        state: region.trim() || undefined,
      });
      setImportResult(result);
      toast("Import complete", "success");
      setText("");
      recent.reload();
    } catch (err) {
      const message = errorMessage(err);
      setImportError(message);
      toast(message, "error");
    } finally {
      setImporting(false);
    }
  };

  const importedRows: any[] = Array.isArray(importResult?.items)
    ? importResult.items
    : Array.isArray(importResult?.created)
      ? importResult.created
      : [];

  return (
    <div>
      <PageHeader
        title="Find vendors"
        subtitle="Run automated discovery or paste a list to import"
        actions={
          <a className="btn btn-sm" href="/vendors">
            Back to vendors
          </a>
        }
      />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card title="Automated discovery">
          <p className="muted mb-3 text-sm">
            Asks the backend to discover new vendors from its configured sources.
          </p>
          <div className="flex items-end gap-2">
            <div className="w-32">
              <Field label="Limit">
                <input
                  className="input"
                  type="number"
                  min={1}
                  max={100}
                  value={limit}
                  onChange={(event) => setLimit(Number(event.target.value))}
                />
              </Field>
            </div>
            <button
              type="button"
              className="btn btn-primary"
              onClick={discover}
              disabled={discovering}
            >
              {discovering ? "Discovering…" : "Discover vendors"}
            </button>
          </div>

          <div className="mt-4">
            <ErrorNote message={discoverError} />
            {discovering ? <Spinner label="Contacting discovery sources…" /> : null}
            {discoverResult ? (
              <div className="space-y-3">
                <p className="text-sm text-emerald-300">Discovery run finished.</p>
                <KeyValues
                  data={Object.fromEntries(
                    Object.entries(discoverResult).filter(([key]) => key !== "items" && key !== "vendors"),
                  )}
                />
                <div className="flex flex-wrap gap-2">
                  {["created", "imported", "discovered", "skipped", "duplicates"].map((key) =>
                    discoverResult[key] !== undefined ? (
                      <span key={key} className="badge badge-indigo">
                        {key}: {String(discoverResult[key])}
                      </span>
                    ) : null,
                  )}
                </div>
              </div>
            ) : null}
          </div>
        </Card>

        <Card title="Paste import">
          <p className="muted mb-3 text-sm">
            One vendor per line, e.g. <span className="mono">Company &lt;email@example.com&gt;</span>.
          </p>
          <Field label="Vendors">
            <textarea
              className="textarea"
              placeholder={"Acme Roofing <info@acme.com>\nBright Plumbing, hello@brightplumb.com"}
              value={text}
              onChange={(event) => setText(event.target.value)}
            />
          </Field>
          <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-3">
            <Field label="Trade (optional)">
              <input className="input" value={trade} onChange={(event) => setTrade(event.target.value)} />
            </Field>
            <Field label="City (optional)">
              <input className="input" value={city} onChange={(event) => setCity(event.target.value)} />
            </Field>
            <Field label="State / region (optional)">
              <input className="input" value={region} onChange={(event) => setRegion(event.target.value)} />
            </Field>
          </div>
          <button
            type="button"
            className="btn btn-primary mt-3"
            onClick={importPaste}
            disabled={importing}
          >
            {importing ? "Importing…" : "Import pasted list"}
          </button>

          <div className="mt-4">
            <ErrorNote message={importError} />
            {importResult ? (
              <div className="space-y-3">
                <p className="text-sm text-emerald-300">Import finished.</p>
                <KeyValues
                  data={Object.fromEntries(
                    Object.entries(importResult).filter(([key]) => !["items", "created", "vendors"].includes(key)),
                  )}
                />
                {importedRows.length > 0 ? (
                  <TableShell>
                    <thead>
                      <tr>
                        <th>Company</th>
                        <th>Email</th>
                        <th>Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {importedRows.slice(0, 10).map((row, index) => (
                        <tr key={row.id || index}>
                          <td>{row.company || "—"}</td>
                          <td className="mono">{row.email || "—"}</td>
                          <td>{row.status || (row.created === false ? "skipped" : "created")}</td>
                        </tr>
                      ))}
                    </tbody>
                  </TableShell>
                ) : null}
              </div>
            ) : null}
          </div>
        </Card>
      </div>

      <div className="mt-4">
        <Card title="Newest vendors" actions={<a className="btn btn-sm" href="/vendors">View all</a>}>
          <ErrorNote message={recent.error} />
          {recent.loading && !recent.data ? <Spinner /> : null}
          {(recent.data?.items ?? []).length === 0 ? (
            <p className="muted text-sm">Nothing imported yet.</p>
          ) : (
            <ul className="divide-y divide-slate-800">
              {(recent.data?.items ?? []).map((vendor: any) => (
                <li key={vendor.id} className="flex items-center justify-between gap-3 py-2 text-sm">
                  <span className="text-slate-100">{vendor.company}</span>
                  <span className="mono text-xs text-slate-400">{vendor.email || "no email"}</span>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </div>
  );
}

export default FindVendorsClient;
