export function fmtNumber(value: unknown): string {
  const num = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(num)) return "0";
  return new Intl.NumberFormat("en-US").format(num);
}

export function fmtPercent(value: unknown, digits = 1): string {
  const num = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(num)) return "0%";
  return `${num.toFixed(digits)}%`;
}

export function fmtDate(value: unknown): string {
  if (!value) return "—";
  const date = new Date(String(value));
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function fmtDateShort(value: unknown): string {
  if (!value) return "—";
  const date = new Date(String(value));
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

export function truncate(value: unknown, max = 60): string {
  const text = value === null || value === undefined ? "" : String(value);
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

/** Percentage of `value` relative to `total`, clamped to 0..100 for bar widths. */
export function pct(value: unknown, total: unknown): number {
  const v = Number(value) || 0;
  const t = Number(total) || 0;
  if (t <= 0) return 0;
  return Math.max(0, Math.min(100, (v / t) * 100));
}

export function statusTone(status: unknown): string {
  const value = String(status || "").toLowerCase();
  if (["active", "sent", "completed", "qualified", "connected", "scheduled", "interested", "replied"].includes(value)) {
    return "badge badge-green";
  }
  if (["pending", "paused", "queued", "warm", "new", "delayed"].includes(value)) {
    return "badge badge-amber";
  }
  if (["failed", "cancelled", "canceled", "opted_out", "bounced", "dead", "error", "not_interested"].includes(value)) {
    return "badge badge-red";
  }
  if (["claimed", "running", "in_progress", "proposed", "invited"].includes(value)) {
    return "badge badge-indigo";
  }
  return "badge badge-slate";
}

export function humanize(value: unknown): string {
  return String(value ?? "")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}
