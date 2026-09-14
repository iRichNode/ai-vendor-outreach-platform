"use client";

import { useEffect, useMemo, useState } from "react";

import { useToast } from "@/components/Toast";
import {
  Card,
  EmptyState,
  ErrorNote,
  Field,
  InfoNote,
  PageHeader,
  Spinner,
} from "@/components/ui";
import { api, errorMessage, type AnyRecord } from "@/lib/api";
import { humanize } from "@/lib/format";
import { useApi } from "@/lib/useApi";

/** { field: { value, type } } as returned by GET /api/settings/schema */
type FieldSpec = { value: unknown; type?: string };
type SchemaMap = Record<string, Record<string, FieldSpec>>;
type Values = Record<string, unknown>;

/** Preferred tab order; any extra sections returned by the backend are appended. */
const SECTION_ORDER = [
  "general",
  "ai",
  "gmail",
  "telegram",
  "discovery",
  "research",
  "dispatch",
  "sending",
  "follow_ups",
  "notifications",
];

const LONG_TEXT = /(prompt|body|template|signature|note|message|instructions|context|system)/i;

function kindOf(spec: FieldSpec | undefined, value: unknown): "bool" | "number" | "json" | "longtext" | "text" {
  const declared = String(spec?.type ?? "").toLowerCase();
  if (typeof value === "boolean" || declared === "bool" || declared === "boolean") return "bool";
  if (typeof value === "number" || declared === "int" || declared === "float" || declared === "number") {
    return "number";
  }
  if (Array.isArray(value) || (value !== null && typeof value === "object")) return "json";
  if (declared === "json" || declared === "list" || declared === "dict") return "json";
  return "text";
}

function toInputValue(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "object") return JSON.stringify(value, null, 2);
  return String(value);
}

export function SettingsClient() {
  const toast = useToast();
  const [section, setSection] = useState<string>("");
  const [form, setForm] = useState<Values>({});
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [bundling, setBundling] = useState(false);

  const settings = useApi(() => api.settings.get(), []);
  const schema = useApi<SchemaMap>(() => api.settings.schema(), []);
  const gmail = useApi(() => api.integrations.gmailStatus(), []);
  const telegram = useApi(() => api.integrations.telegramStatus(), []);

  // Memoised so the effects below keep stable dependencies (avoids render loops while
  // one of the two requests is still pending or has failed).
  const current: Values = useMemo(
    () => ((settings.data?.settings as Values) ?? {}),
    [settings.data],
  );
  const schemaMap: SchemaMap = useMemo(
    () => ((schema.data as SchemaMap) ?? (settings.data?.schema as SchemaMap) ?? {}),
    [schema.data, settings.data],
  );

  const sections = useMemo(() => {
    const keys = new Set<string>([...Object.keys(schemaMap), ...Object.keys(current)]);
    const ordered = SECTION_ORDER.filter((key) => keys.has(key));
    const extras = [...keys].filter((key) => !SECTION_ORDER.includes(key)).sort();
    return [...ordered, ...extras];
  }, [schemaMap, current]);

  // Keep the active tab valid once the schema/settings arrive.
  useEffect(() => {
    if (!section && sections.length) setSection(sections[0]);
    if (section && sections.length && !sections.includes(section)) setSection(sections[0]);
  }, [section, sections]);

  // Reset the form whenever the active section or the server payload changes.
  useEffect(() => {
    if (!section) return;
    const spec = (schemaMap[section] ?? {}) as Record<string, FieldSpec>;
    const values = (current[section] ?? {}) as Values;
    const keys = new Set<string>([...Object.keys(spec), ...Object.keys(values)]);
    const next: Values = {};
    for (const key of keys) {
      const specEntry = spec[key];
      next[key] = values[key] !== undefined ? values[key] : specEntry?.value;
    }
    setForm(next);
  }, [section, schemaMap, current]);

  const fieldKeys = Object.keys(form);
  const activeGmail = gmail.data as AnyRecord | undefined;

  const setField = (key: string, value: unknown) => setForm((prev) => ({ ...prev, [key]: value }));

  const save = async () => {
    if (!section) return;
    const payload: Values = {};
    for (const [key, value] of Object.entries(form)) {
      const spec = schemaMap[section]?.[key];
      if (kindOf(spec, value) === "json" && typeof value === "string") {
        try {
          payload[key] = value.trim() === "" ? null : JSON.parse(value);
        } catch {
          toast(`${humanize(key)}: invalid JSON`, "error");
          return;
        }
      } else {
        payload[key] = value;
      }
    }

    setSaving(true);
    try {
      await api.settings.updateSection(section, payload);
      toast(`${humanize(section)} settings saved`, "success");
      settings.reload();
    } catch (err) {
      toast(errorMessage(err), "error");
    } finally {
      setSaving(false);
    }
  };

  const testTelegram = async () => {
    setTesting(true);
    try {
      const result: AnyRecord = await api.integrations.telegramTest();
      toast(result?.ok ? `Telegram OK: ${result.detail ?? "sent"}` : `Telegram failed: ${result?.detail ?? "unknown"}`, result?.ok ? "success" : "error");
      telegram.reload();
    } catch (err) {
      toast(errorMessage(err), "error");
    } finally {
      setTesting(false);
    }
  };

  const connectGmail = async () => {
    setBundling(true);
    try {
      const result: AnyRecord = await api.integrations.gmailAuthUrl(
        `${window.location.origin}/settings`,
      );
      if (result?.auth_url) {
        window.location.href = String(result.auth_url);
      } else {
        toast("Backend did not return an auth_url", "error");
      }
    } catch (err) {
      toast(errorMessage(err), "error");
    } finally {
      setBundling(false);
    }
  };

  const disconnectGmail = async () => {
    if (!window.confirm("Disconnect Gmail and remove stored credentials?")) return;
    setBundling(true);
    try {
      await api.integrations.gmailDisconnect();
      toast("Gmail disconnected", "success");
      gmail.reload();
    } catch (err) {
      toast(errorMessage(err), "error");
    } finally {
      setBundling(false);
    }
  };

  const error = settings.error ?? schema.error;

  return (
    <div>
      <PageHeader
        title="Settings"
        subtitle="Runtime configuration — saved per section with a full-key PUT"
        actions={
          <button
            type="button"
            className="btn btn-primary"
            onClick={save}
            disabled={saving || !section || fieldKeys.length === 0}
          >
            {saving ? "Saving…" : `Save ${section ? humanize(section) : ""}`}
          </button>
        }
      />

      <ErrorNote message={error} />

      <div className="grid grid-cols-1 gap-3 xl:grid-cols-3">
        <Card title="Integrations">
          <div className="space-y-4">
            <div className="rounded-md border border-slate-800 bg-slate-900/40 p-3">
              <div className="flex items-center justify-between">
                <span className="text-sm font-semibold text-slate-100">Gmail</span>
                {gmail.loading && !gmail.data ? (
                  <span className="muted text-xs">checking…</span>
                ) : (
                  <span className={`badge ${activeGmail?.configured ? "badge-green" : "badge-slate"}`}>
                    {activeGmail?.configured ? "configured" : "not configured"}
                  </span>
                )}
              </div>
              <p className="muted mt-1 text-xs">
                transport: <span className="mono">{String(activeGmail?.transport ?? "—")}</span> • demo
                mode: <span className="mono">{String(activeGmail?.demo_mode ?? "—")}</span>
              </p>
              <p className="muted mt-1 text-xs">
                accounts:{" "}
                <span className="mono">
                  {Array.isArray(activeGmail?.accounts) && activeGmail?.accounts.length
                    ? activeGmail.accounts
                        .map((account: AnyRecord) => account.email)
                        .filter(Boolean)
                        .join(", ")
                    : "none"}
                </span>
              </p>
              <div className="mt-3 flex flex-wrap gap-2">
                <button type="button" className="btn btn-sm" onClick={connectGmail} disabled={bundling}>
                  {bundling ? "Working…" : "Connect Gmail"}
                </button>
                <button
                  type="button"
                  className="btn btn-sm btn-danger"
                  onClick={disconnectGmail}
                  disabled={bundling}
                >
                  Disconnect
                </button>
              </div>
              <ErrorNote message={gmail.error} />
            </div>

            <div className="rounded-md border border-slate-800 bg-slate-900/40 p-3">
              <div className="flex items-center justify-between">
                <span className="text-sm font-semibold text-slate-100">Telegram</span>
                {telegram.loading && !telegram.data ? (
                  <span className="muted text-xs">checking…</span>
                ) : (
                  <span
                    className={`badge ${telegram.data?.configured ? "badge-green" : "badge-slate"}`}
                  >
                    {telegram.data?.configured ? "configured" : "not configured"}
                  </span>
                )}
              </div>
              <p className="muted mt-1 text-xs">
                bot token: <span className="mono">{String(telegram.data?.token_configured ?? "—")}</span>{" "}
                • chat id: <span className="mono">{String(telegram.data?.chat_id_configured ?? "—")}</span>
              </p>
              <div className="mt-3">
                <button
                  type="button"
                  className="btn btn-sm btn-primary"
                  onClick={testTelegram}
                  disabled={testing}
                >
                  {testing ? "Sending test…" : "Send test message"}
                </button>
              </div>
              <ErrorNote message={telegram.error} />
            </div>
          </div>
        </Card>

        <div className="xl:col-span-2">
          <Card
            title="Configuration"
            actions={
              <button
                type="button"
                className="btn btn-sm"
                onClick={() => {
                  settings.reload();
                  schema.reload();
                }}
              >
                Refresh
              </button>
            }
          >
            {settings.loading && !settings.data && schema.loading ? (
              <Spinner label="Loading settings…" />
            ) : null}

            {!settings.loading && sections.length === 0 ? (
              <EmptyState
                message="No settings sections returned by the backend."
                hint="GET /api/settings/schema returned an empty schema."
              />
            ) : null}

            {sections.length > 0 ? (
              <>
                <div className="mb-4 flex flex-wrap gap-2 border-b border-slate-800 pb-2">
                  {sections.map((key) => (
                    <button
                      key={key}
                      type="button"
                      className={`badge ${key === section ? "badge-indigo" : "badge-slate"} cursor-pointer`}
                      onClick={() => setSection(key)}
                    >
                      {humanize(key)}
                    </button>
                  ))}
                </div>

                {fieldKeys.length === 0 ? (
                  <EmptyState message={`${humanize(section)} has no editable fields.`} />
                ) : (
                  <div className="space-y-3">
                    {fieldKeys.map((key) => {
                      const spec = schemaMap[section]?.[key];
                      const value = form[key];
                      const kind = kindOf(spec, value);
                      const label = humanize(key);
                      const hint =
                        spec && typeof (spec as AnyRecord).description === "string"
                          ? String((spec as AnyRecord).description)
                          : kind === "json"
                            ? "JSON value — parsed before saving."
                            : undefined;
                      const fieldKey = `${section}.${key}`;

                      if (kind === "bool") {
                        return (
                          <label
                            key={fieldKey}
                            className="flex items-center gap-3 rounded-md border border-slate-800 bg-slate-900/40 px-3 py-2"
                          >
                            <input
                              type="checkbox"
                              checked={Boolean(value)}
                              onChange={(event) => setField(key, event.target.checked)}
                            />
                            <span className="text-sm text-slate-200">{label}</span>
                            <span className="muted ml-auto text-xs">boolean</span>
                          </label>
                        );
                      }

                      if (kind === "number") {
                        return (
                          <Field key={fieldKey} label={label} hint={hint}>
                            <input
                              className="input"
                              type="number"
                              step="any"
                              value={toInputValue(value)}
                              onChange={(event) =>
                                setField(
                                  key,
                                  event.target.value === "" ? null : Number(event.target.value),
                                )
                              }
                            />
                          </Field>
                        );
                      }

                      if (kind === "json" || LONG_TEXT.test(key) || toInputValue(value).length > 90) {
                        return (
                          <Field key={fieldKey} label={label} hint={hint}>
                            <textarea
                              className="textarea mono"
                              spellCheck={false}
                              value={typeof value === "object" ? JSON.stringify(value, null, 2) : toInputValue(value)}
                              onChange={(event) => setField(key, event.target.value)}
                            />
                          </Field>
                        );
                      }

                      return (
                        <Field key={fieldKey} label={label} hint={hint}>
                          <input
                            className="input"
                            value={toInputValue(value)}
                            onChange={(event) => setField(key, event.target.value)}
                          />
                        </Field>
                      );
                    })}
                  </div>
                )}

                <InfoNote>
                  Saving sends <span className="mono">PUT /api/settings/{section || "…"}</span> with{" "}
                  <span className="mono">{`{"section": "...", "values": {...}}`}</span>. Keys must be
                  discoverable by the backend schema, so every field is submitted with the form.
                </InfoNote>
              </>
            ) : null}
          </Card>
        </div>
      </div>
    </div>
  );
}

export default SettingsClient;
