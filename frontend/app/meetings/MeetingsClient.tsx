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
import { MEETING_STATUSES } from "@/lib/constants";
import { fmtDate, fmtNumber, truncate } from "@/lib/format";
import { useApi } from "@/lib/useApi";

export function MeetingsClient() {
  const toast = useToast();
  const [status, setStatus] = useState("");
  const [busyId, setBusyId] = useState<string | null>(null);
  const [scheduleOpen, setScheduleOpen] = useState<any | null>(null);
  const [scheduledTime, setScheduledTime] = useState("");
  const [cancelOpen, setCancelOpen] = useState<any | null>(null);
  const [cancelReason, setCancelReason] = useState("");

  const meetings = useApi(
    () => api.meetings.list({ status: status || undefined, limit: 100 }),
    [status],
  );

  const items: any[] = meetings.data?.items ?? [];

  const run = async (
    meeting: any,
    action: "send-invitation" | "complete",
    label: string,
  ) => {
    if (action === "complete" && !window.confirm("Mark this meeting as completed?")) return;
    setBusyId(meeting.id);
    try {
      if (action === "send-invitation") await api.meetings.sendInvitation(meeting.id);
      else await api.meetings.complete(meeting.id);
      toast(`${label} done`, "success");
      meetings.reload();
    } catch (err) {
      toast(errorMessage(err), "error");
    } finally {
      setBusyId(null);
    }
  };

  const markScheduled = async () => {
    if (!scheduleOpen) return;
    setBusyId(scheduleOpen.id);
    try {
      await api.meetings.markScheduled(
        scheduleOpen.id,
        scheduledTime ? new Date(scheduledTime).toISOString() : null,
      );
      toast("Meeting marked as scheduled", "success");
      setScheduleOpen(null);
      setScheduledTime("");
      meetings.reload();
    } catch (err) {
      toast(errorMessage(err), "error");
    } finally {
      setBusyId(null);
    }
  };

  const cancelMeeting = async () => {
    if (!cancelOpen) return;
    setBusyId(cancelOpen.id);
    try {
      await api.meetings.cancel(cancelOpen.id, cancelReason);
      toast("Meeting cancelled", "success");
      setCancelOpen(null);
      setCancelReason("");
      meetings.reload();
    } catch (err) {
      toast(errorMessage(err), "error");
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div>
      <PageHeader
        title="Meetings"
        subtitle={`${fmtNumber(meetings.data?.total ?? items.length)} meeting(s)`}
        actions={
          <select
            className="select w-48"
            value={status}
            onChange={(event) => setStatus(event.target.value)}
            aria-label="Filter meetings by status"
          >
            <option value="">All statuses</option>
            {MEETING_STATUSES.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        }
      />

      <Card>
        <ErrorNote message={meetings.error} />
        {meetings.loading && !meetings.data ? <Spinner label="Loading meetings…" /> : null}
        {meetings.data && items.length === 0 ? (
          <EmptyState
            message="No meetings yet."
            hint="Meetings are created from a conversation once a vendor requests one."
          />
        ) : null}

        {items.length > 0 ? (
          <TableShell>
            <thead>
              <tr>
                <th>Company</th>
                <th>Contact</th>
                <th>Status</th>
                <th>Meeting link</th>
                <th>Scheduled</th>
                <th>Invitation sent</th>
                <th>Created</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {items.map((meeting) => (
                <tr key={meeting.id}>
                  <td className="text-slate-100">{meeting.vendor?.company || "—"}</td>
                  <td>
                    {meeting.vendor?.contact_name || "—"}
                    <p className="mono text-xs text-slate-500">{meeting.vendor?.email || ""}</p>
                  </td>
                  <td>
                    <StatusBadge status={meeting.status} />
                  </td>
                  <td>
                    {meeting.meeting_url ? (
                      <a
                        className="mono text-xs text-indigo-300 hover:underline"
                        href={meeting.meeting_url}
                        target="_blank"
                        rel="noreferrer"
                      >
                        {truncate(meeting.meeting_url, 30)}
                      </a>
                    ) : (
                      <span className="muted text-xs">—</span>
                    )}
                  </td>
                  <td className="muted text-xs">{fmtDate(meeting.scheduled_time)}</td>
                  <td className="muted text-xs">{fmtDate(meeting.invitation_sent_at)}</td>
                  <td className="muted text-xs">{fmtDate(meeting.created_at)}</td>
                  <td>
                    <div className="flex flex-wrap gap-1">
                      <button
                        type="button"
                        className="btn btn-sm"
                        onClick={() => run(meeting, "send-invitation", "Invitation sent")}
                        disabled={busyId === meeting.id}
                      >
                        Send invitation
                      </button>
                      <button
                        type="button"
                        className="btn btn-sm btn-primary"
                        onClick={() => {
                          setScheduleOpen(meeting);
                          setScheduledTime("");
                        }}
                        disabled={busyId === meeting.id}
                      >
                        Mark scheduled
                      </button>
                      <button
                        type="button"
                        className="btn btn-sm"
                        onClick={() => run(meeting, "complete", "Completed")}
                        disabled={busyId === meeting.id}
                      >
                        Complete
                      </button>
                      <button
                        type="button"
                        className="btn btn-sm btn-danger"
                        onClick={() => {
                          setCancelOpen(meeting);
                          setCancelReason("");
                        }}
                        disabled={busyId === meeting.id}
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
      </Card>

      <Modal
        title="Mark meeting as scheduled"
        open={scheduleOpen !== null}
        onClose={() => setScheduleOpen(null)}
        footer={
          <>
            <button type="button" className="btn" onClick={() => setScheduleOpen(null)}>
              Cancel
            </button>
            <button
              type="button"
              className="btn btn-primary"
              onClick={markScheduled}
              disabled={busyId !== null}
            >
              Save
            </button>
          </>
        }
      >
        <p className="muted text-sm">
          {scheduleOpen?.vendor?.company || "Meeting"} — {scheduleOpen?.meeting_url || "no link yet"}
        </p>
        <Field label="Scheduled time" hint="Leave empty to keep the backend default.">
          <input
            className="input"
            type="datetime-local"
            value={scheduledTime}
            onChange={(event) => setScheduledTime(event.target.value)}
          />
        </Field>
      </Modal>

      <Modal
        title="Cancel meeting"
        open={cancelOpen !== null}
        onClose={() => setCancelOpen(null)}
        footer={
          <>
            <button type="button" className="btn" onClick={() => setCancelOpen(null)}>
              Keep meeting
            </button>
            <button
              type="button"
              className="btn btn-danger"
              onClick={cancelMeeting}
              disabled={busyId !== null}
            >
              Cancel meeting
            </button>
          </>
        }
      >
        <Field label="Reason">
          <textarea
            className="textarea"
            value={cancelReason}
            onChange={(event) => setCancelReason(event.target.value)}
          />
        </Field>
      </Modal>
    </div>
  );
}

export default MeetingsClient;
