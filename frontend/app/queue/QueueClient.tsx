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
  StatCard,
  StatusBadge,
  TableShell,
} from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { JOB_STATUSES, JOB_TYPES } from "@/lib/constants";
import { fmtDate, fmtNumber, truncate } from "@/lib/format";
import { useApi } from "@/lib/useApi";

const PAGE_SIZE = 25;

const STAT_KEYS: { key: string; tone: "indigo" | "amber" | "green" | "red" | "slate" }[] = [
  { key: "total", tone: "indigo" },
  { key: "pending", tone: "amber" },
  { key: "claimed", tone: "indigo" },
  { key: "paused", tone: "amber" },
  { key: "failed", tone: "red" },
  { key: "cancelled", tone: "slate" },
  { key: "completed", tone: "green" },
];

export function QueueClient() {
  const toast = useToast();
  const [status, setStatus] = useState("");
  const [jobType, setJobType] = useState("");
  const [offset, setOffset] = useState(0);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [rescheduleJob, setRescheduleJob] = useState<any | null>(null);
  const [runAfter, setRunAfter] = useState("");
  const [reason, setReason] = useState("");
  const [pausing, setPausing] = useState(false);

  const stats = useApi(() => api.queue.stats(), []);
  const jobs = useApi(
    () =>
      api.queue.list({
        status: status || undefined,
        job_type: jobType || undefined,
        limit: PAGE_SIZE,
        offset,
      }),
    [status, jobType, offset],
  );

  const items: any[] = jobs.data?.items ?? [];
  const total = Number(jobs.data?.total ?? items.length);
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const globalPaused = Boolean(stats.data?.global_paused);

  const refresh = () => {
    jobs.reload();
    stats.reload();
  };

  const jobAction = async (job: any, action: "pause" | "resume" | "cancel" | "retry") => {
    if (action === "cancel" && !window.confirm("Cancel this job?")) return;
    setBusyId(job.id);
    try {
      await api.queue[action](job.id);
      toast(`Job ${action}d`, "success");
      refresh();
    } catch (err) {
      toast(errorMessage(err), "error");
    } finally {
      setBusyId(null);
    }
  };

  const toggleGlobalPause = async () => {
    setPausing(true);
    try {
      await api.queue.setGlobalPause(!globalPaused);
      toast(globalPaused ? "Queue resumed" : "Queue paused globally", "success");
      refresh();
    } catch (err) {
      toast(errorMessage(err), "error");
    } finally {
      setPausing(false);
    }
  };

  const submitReschedule = async () => {
    if (!rescheduleJob || !runAfter) {
      toast("Pick a date and time.", "error");
      return;
    }
    setBusyId(rescheduleJob.id);
    try {
      await api.queue.reschedule(
        rescheduleJob.id,
        new Date(runAfter).toISOString(),
        reason.trim() || undefined,
      );
      toast("Job rescheduled", "success");
      setRescheduleJob(null);
      setRunAfter("");
      setReason("");
      refresh();
    } catch (err) {
      toast(errorMessage(err), "error");
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div>
      <PageHeader
        title="Queue"
        subtitle="Scheduled jobs and the global dispatch switch"
        actions={
          <button
            type="button"
            className={`btn btn-sm ${globalPaused ? "btn-primary" : "btn-danger"}`}
            onClick={toggleGlobalPause}
            disabled={pausing}
          >
            {pausing ? "Working…" : globalPaused ? "Resume queue" : "Pause queue"}
          </button>
        }
      />

      <ErrorNote message={stats.error} />

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 xl:grid-cols-7">
        {STAT_KEYS.map(({ key, tone }) => (
          <StatCard
            key={key}
            label={key}
            value={stats.loading && !stats.data ? "…" : fmtNumber(stats.data?.[key] ?? 0)}
            tone={tone}
          />
        ))}
      </div>

      <div className="mt-4">
        <Card
          title="Jobs"
          actions={
            <div className="flex flex-wrap items-end gap-2">
              <select
                className="select w-40"
                value={status}
                onChange={(event) => {
                  setStatus(event.target.value);
                  setOffset(0);
                }}
                aria-label="Filter by status"
              >
                <option value="">All statuses</option>
                {JOB_STATUSES.map((value) => (
                  <option key={value} value={value}>
                    {value}
                  </option>
                ))}
              </select>
              <select
                className="select w-44"
                value={jobType}
                onChange={(event) => {
                  setJobType(event.target.value);
                  setOffset(0);
                }}
                aria-label="Filter by job type"
              >
                <option value="">All job types</option>
                {JOB_TYPES.map((value) => (
                  <option key={value} value={value}>
                    {value}
                  </option>
                ))}
              </select>
            </div>
          }
        >
          <ErrorNote message={jobs.error} />
          {jobs.loading && !jobs.data ? <Spinner label="Loading queue…" /> : null}
          {jobs.data && items.length === 0 ? (
            <EmptyState message="No jobs match the current filter." />
          ) : null}

          {items.length > 0 ? (
            <TableShell>
              <thead>
                <tr>
                  <th>Type</th>
                  <th>Status</th>
                  <th>Campaign</th>
                  <th>Vendor</th>
                  <th>Run after</th>
                  <th>Attempts</th>
                  <th>Last error</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {items.map((job) => (
                  <tr key={job.id}>
                    <td className="mono">{job.job_type}</td>
                    <td>
                      <StatusBadge status={job.status} />
                    </td>
                    <td className="mono text-xs">{job.campaign_id ? truncate(job.campaign_id, 12) : "—"}</td>
                    <td className="mono text-xs">{job.vendor_id ? truncate(job.vendor_id, 12) : "—"}</td>
                    <td className="muted text-xs">{fmtDate(job.run_after)}</td>
                    <td className="mono">
                      {fmtNumber(job.attempts ?? 0)}
                      {job.max_attempts ? `/${job.max_attempts}` : ""}
                    </td>
                    <td className="text-xs text-rose-300">{job.last_error ? truncate(job.last_error, 40) : "—"}</td>
                    <td>
                      <div className="flex flex-wrap gap-1">
                        <button
                          type="button"
                          className="btn btn-sm"
                          onClick={() => jobAction(job, "pause")}
                          disabled={busyId === job.id}
                        >
                          Pause
                        </button>
                        <button
                          type="button"
                          className="btn btn-sm"
                          onClick={() => jobAction(job, "resume")}
                          disabled={busyId === job.id}
                        >
                          Resume
                        </button>
                        <button
                          type="button"
                          className="btn btn-sm"
                          onClick={() => jobAction(job, "retry")}
                          disabled={busyId === job.id}
                        >
                          Retry
                        </button>
                        <button
                          type="button"
                          className="btn btn-sm"
                          onClick={() => {
                            setRescheduleJob(job);
                            setRunAfter("");
                            setReason("");
                          }}
                          disabled={busyId === job.id}
                        >
                          Reschedule
                        </button>
                        <button
                          type="button"
                          className="btn btn-sm btn-danger"
                          onClick={() => jobAction(job, "cancel")}
                          disabled={busyId === job.id}
                        >
                          Cancel
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

      <Modal
        title="Reschedule job"
        open={rescheduleJob !== null}
        onClose={() => setRescheduleJob(null)}
        footer={
          <>
            <button type="button" className="btn" onClick={() => setRescheduleJob(null)}>
              Cancel
            </button>
            <button
              type="button"
              className="btn btn-primary"
              onClick={submitReschedule}
              disabled={busyId !== null}
            >
              {busyId !== null ? "Saving…" : "Reschedule"}
            </button>
          </>
        }
      >
        <p className="muted text-sm">
          Job <span className="mono">{rescheduleJob?.job_type}</span> —{" "}
          <span className="mono">{rescheduleJob?.id ? truncate(rescheduleJob.id, 14) : ""}</span>
        </p>
        <Field label="Run after *">
          <input
            className="input"
            type="datetime-local"
            value={runAfter}
            onChange={(event) => setRunAfter(event.target.value)}
          />
        </Field>
        <Field label="Reason">
          <input className="input" value={reason} onChange={(event) => setReason(event.target.value)} />
        </Field>
      </Modal>
    </div>
  );
}

export default QueueClient;
