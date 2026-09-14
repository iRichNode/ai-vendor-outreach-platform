"use client";

import type { ReactNode } from "react";

import { humanize, statusTone } from "@/lib/format";

export function PageHeader({
  title,
  subtitle,
  actions,
}: {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">{title}</h1>
        {subtitle ? <p className="muted mt-1 text-sm">{subtitle}</p> : null}
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
    </div>
  );
}

export function Card({
  title,
  actions,
  children,
  className = "",
}: {
  title?: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`card ${className}`}>
      {title || actions ? (
        <header className="mb-3 flex items-center justify-between gap-3">
          {title ? <h2 className="text-sm font-semibold text-slate-100">{title}</h2> : <span />}
          {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
        </header>
      ) : null}
      {children}
    </section>
  );
}

export function StatCard({
  label,
  value,
  hint,
  tone = "indigo",
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  tone?: "indigo" | "green" | "amber" | "red" | "slate";
}) {
  const accent: Record<string, string> = {
    indigo: "border-l-indigo-500",
    green: "border-l-emerald-500",
    amber: "border-l-amber-500",
    red: "border-l-rose-500",
    slate: "border-l-slate-500",
  };
  return (
    <div className={`card border-l-4 ${accent[tone]}`}>
      <p className="card-title">{label}</p>
      <p className="stat-value">{value}</p>
      {hint ? <p className="muted mt-1 text-xs">{hint}</p> : null}
    </div>
  );
}

export function Bar({
  value,
  total,
  color = "#6366f1",
  label,
}: {
  value: number;
  total: number;
  color?: string;
  label?: string;
}) {
  const width = total > 0 ? Math.max(0, Math.min(100, (value / total) * 100)) : 0;
  return (
    <div>
      {label ? (
        <div className="mb-1 flex items-center justify-between text-xs">
          <span className="muted">{label}</span>
          <span className="mono text-slate-300">{value}</span>
        </div>
      ) : null}
      <div className="bar-track">
        <div className="bar-fill" style={{ width: `${width}%`, backgroundColor: color }} />
      </div>
    </div>
  );
}

export function StatusBadge({ status }: { status: unknown }) {
  const text = String(status ?? "unknown");
  return <span className={statusTone(text)}>{humanize(text)}</span>;
}

export function Spinner({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 py-6 text-sm text-slate-400">
      <span className="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-slate-600 border-t-indigo-400" />
      {label}
    </div>
  );
}

export function ErrorNote({ message }: { message: string | null }) {
  if (!message) return null;
  return <div className="alert mb-3">{message}</div>;
}

export function InfoNote({ children }: { children: ReactNode }) {
  if (!children) return null;
  return <div className="alert alert-info mb-3">{children}</div>;
}

export function EmptyState({ message, hint }: { message: string; hint?: string }) {
  return (
    <div className="rounded-lg border border-dashed border-slate-700 px-4 py-8 text-center">
      <p className="text-sm text-slate-300">{message}</p>
      {hint ? <p className="muted mt-1 text-xs">{hint}</p> : null}
    </div>
  );
}

export function Modal({
  title,
  open,
  onClose,
  children,
  footer,
}: {
  title: string;
  open: boolean;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
}) {
  if (!open) return null;
  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label={title}>
      <div className="modal-panel">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold">{title}</h2>
          <button type="button" className="btn btn-sm" onClick={onClose} aria-label="Close">
            ✕
          </button>
        </div>
        <div className="space-y-3">{children}</div>
        {footer ? <div className="mt-5 flex justify-end gap-2">{footer}</div> : null}
      </div>
    </div>
  );
}

export function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <label className="block">
      <span className="label">{label}</span>
      {children}
      {hint ? <span className="muted mt-1 block text-xs">{hint}</span> : null}
    </label>
  );
}

export function TableShell({ children }: { children: ReactNode }) {
  return (
    <div className="-mx-1 overflow-x-auto">
      <table className="table">{children}</table>
    </div>
  );
}

export function KeyValues({ data }: { data: Record<string, unknown> }) {
  const entries = Object.entries(data || {}).filter(([, value]) => value !== undefined);
  if (!entries.length) return <p className="muted text-sm">No data.</p>;
  return (
    <dl className="grid grid-cols-1 gap-2 sm:grid-cols-2">
      {entries.map(([key, value]) => (
        <div key={key} className="rounded-md border border-slate-800 bg-slate-900/40 px-3 py-2">
          <dt className="muted text-xs uppercase tracking-wide">{humanize(key)}</dt>
          <dd className="mono mt-0.5 break-words text-slate-200">
            {typeof value === "object" ? JSON.stringify(value) : String(value ?? "—")}
          </dd>
        </div>
      ))}
    </dl>
  );
}
