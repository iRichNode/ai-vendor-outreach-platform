"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

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
  StatusBadge,
} from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { CONVERSATION_ACTIONS } from "@/lib/constants";
import { fmtDate, humanize } from "@/lib/format";
import { useApi } from "@/lib/useApi";

interface Message {
  id?: string;
  direction?: string;
  body?: string;
  subject?: string;
  origin?: string;
  created_at?: string;
  received_at?: string;
  delivery_state?: string;
}

function isOutbound(message: Message): boolean {
  return String(message.direction || "").toUpperCase() === "OUTBOUND";
}

export function ConversationDetailClient({ id }: { id: string }) {
  const toast = useToast();
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [linkOpen, setLinkOpen] = useState(false);
  const [meetingUrl, setMeetingUrl] = useState("");
  const [meetingNotes, setMeetingNotes] = useState("");
  const [noteOpen, setNoteOpen] = useState(false);
  const [note, setNote] = useState("");
  const threadEnd = useRef<HTMLDivElement | null>(null);

  const detail = useApi(() => api.conversations.get(id), [id]);

  const conversation = detail.data ?? {};
  const vendor = conversation.vendor ?? {};
  const messages: Message[] = conversation.messages ?? [];

  useEffect(() => {
    if (messages.length && threadEnd.current) {
      threadEnd.current.scrollIntoView({ behavior: "smooth", block: "end" });
    }
  }, [messages.length]);

  const send = async () => {
    if (!draft.trim()) return;
    setSending(true);
    try {
      await api.conversations.sendMessage(id, draft);
      setDraft("");
      toast("Message queued", "success");
      detail.reload();
    } catch (err) {
      toast(errorMessage(err), "error");
    } finally {
      setSending(false);
    }
  };

  const runAction = async (action: string, danger?: boolean) => {
    if (danger && !window.confirm(`Confirm “${action}”?`)) return;
    setBusy(action);
    try {
      await api.conversations.action(id, action);
      toast(`Action “${action}” applied`, "success");
      detail.reload();
    } catch (err) {
      toast(errorMessage(err), "error");
    } finally {
      setBusy(null);
    }
  };

  const markInterest = async (interested: boolean) => {
    setBusy(interested ? "interest" : "no-interest");
    try {
      await api.conversations.markInterest(id, interested);
      toast(interested ? "Marked interested" : "Marked not interested", "success");
      detail.reload();
    } catch (err) {
      toast(errorMessage(err), "error");
    } finally {
      setBusy(null);
    }
  };

  const markQualified = async (qualified: boolean) => {
    setBusy(qualified ? "qualified" : "unqualified");
    try {
      await api.conversations.markQualified(id, qualified);
      toast(qualified ? "Marked qualified" : "Marked not qualified", "success");
      detail.reload();
    } catch (err) {
      toast(errorMessage(err), "error");
    } finally {
      setBusy(null);
    }
  };

  const saveMeetingLink = async () => {
    if (!meetingUrl.trim()) {
      toast("Meeting URL is required.", "error");
      return;
    }
    setBusy("link");
    try {
      await api.conversations.meetingLink(id, meetingUrl.trim(), meetingNotes.trim() || undefined);
      toast("Meeting link saved", "success");
      setLinkOpen(false);
      setMeetingUrl("");
      setMeetingNotes("");
      detail.reload();
    } catch (err) {
      toast(errorMessage(err), "error");
    } finally {
      setBusy(null);
    }
  };

  const saveNote = async () => {
    if (!note.trim()) {
      toast("Note cannot be empty.", "error");
      return;
    }
    setBusy("note");
    try {
      await api.conversations.addNote(id, note.trim());
      toast("Note added", "success");
      setNoteOpen(false);
      setNote("");
      detail.reload();
    } catch (err) {
      toast(errorMessage(err), "error");
    } finally {
      setBusy(null);
    }
  };

  if (detail.loading && !detail.data) return <Spinner label="Loading conversation…" />;

  return (
    <div>
      <PageHeader
        title={vendor.company || conversation.subject || "Conversation"}
        subtitle={conversation.subject || ""}
        actions={
          <>
            <Link className="btn btn-sm" href="/conversations">
              Back
            </Link>
            <StatusBadge status={conversation.status} />
          </>
        }
      />

      <ErrorNote message={detail.error} />

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[2fr_1fr]">
        <Card title={`Thread (${messages.length})`}>
          {messages.length === 0 ? (
            <EmptyState message="No messages in this thread yet." />
          ) : (
            <div className="flex max-h-[32rem] flex-col gap-3 overflow-y-auto pr-1">
              {messages.map((message, index) => (
                <div
                  key={message.id || index}
                  className={`flex flex-col gap-1 ${isOutbound(message) ? "items-end" : "items-start"}`}
                >
                  <div className="flex items-center gap-2 text-xs">
                    <span className="muted">{fmtDate(message.created_at || message.received_at)}</span>
                    <span className={message.origin === "AI" ? "badge badge-indigo" : "badge badge-slate"}>
                      {humanize(message.origin || message.direction || "")}
                    </span>
                    {message.delivery_state ? (
                      <span className="muted">{humanize(message.delivery_state)}</span>
                    ) : null}
                  </div>
                  <div className={`bubble ${isOutbound(message) ? "bubble-out" : "bubble-in"}`}>
                    {message.body || "(empty)"}
                  </div>
                </div>
              ))}
              <div ref={threadEnd} />
            </div>
          )}

          <div className="mt-4 border-t border-slate-800 pt-3">
            <Field label="Reply as operator">
              <textarea
                className="textarea"
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                placeholder="Type your reply…"
                onKeyDown={(event) => {
                  if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) send();
                }}
              />
            </Field>
            <div className="mt-2 flex items-center justify-between">
              <span className="muted text-xs">⌘/Ctrl + Enter to send</span>
              <button type="button" className="btn btn-primary" onClick={send} disabled={sending}>
                {sending ? "Sending…" : "Send message"}
              </button>
            </div>
          </div>
        </Card>

        <div className="space-y-4">
          <Card title="Vendor">
            <KeyValues
              data={{
                company: vendor.company,
                contact_name: vendor.contact_name,
                email: vendor.email,
                phone: vendor.phone,
                city: vendor.city,
                website: vendor.website,
                status: vendor.status,
                qualification_status: vendor.qualification_status,
              }}
            />
          </Card>

          <Card title="AI & handoff">
            <div className="mb-3 flex flex-wrap gap-1">
              <span className={conversation.ai_paused ? "badge badge-amber" : "badge badge-green"}>
                {conversation.ai_paused ? "ai paused" : "ai active"}
              </span>
              <span className={conversation.human_controlled ? "badge badge-indigo" : "badge badge-slate"}>
                {conversation.human_controlled ? "human controlled" : "ai controlled"}
              </span>
              {conversation.qualification_status ? (
                <span className="badge badge-green">{humanize(conversation.qualification_status)}</span>
              ) : null}
            </div>
            <div className="flex flex-wrap gap-1">
              {CONVERSATION_ACTIONS.map((item) => (
                <button
                  key={item.action}
                  type="button"
                  className={`btn btn-sm ${item.danger ? "btn-danger" : ""}`}
                  onClick={() => runAction(item.action, item.danger)}
                  disabled={busy !== null}
                >
                  {busy === item.action ? "…" : item.label}
                </button>
              ))}
            </div>
            <div className="mt-3 flex flex-wrap gap-1 border-t border-slate-800 pt-3">
              <button
                type="button"
                className="btn btn-sm"
                onClick={() => markInterest(true)}
                disabled={busy !== null}
              >
                Mark interested
              </button>
              <button
                type="button"
                className="btn btn-sm"
                onClick={() => markInterest(false)}
                disabled={busy !== null}
              >
                Not interested
              </button>
              <button
                type="button"
                className="btn btn-sm"
                onClick={() => markQualified(true)}
                disabled={busy !== null}
              >
                Mark qualified
              </button>
              <button
                type="button"
                className="btn btn-sm"
                onClick={() => markQualified(false)}
                disabled={busy !== null}
              >
                Not qualified
              </button>
              <button type="button" className="btn btn-sm btn-primary" onClick={() => setLinkOpen(true)}>
                Meeting link
              </button>
              <button type="button" className="btn btn-sm" onClick={() => setNoteOpen(true)}>
                Add note
              </button>
            </div>
          </Card>

          <Card title="Timeline">
            <KeyValues
              data={{
                created: fmtDate(conversation.created_at),
                updated: fmtDate(conversation.updated_at),
                last_inbound: fmtDate(conversation.last_inbound_at),
                last_outbound: fmtDate(conversation.last_outbound_at),
                next_follow_up: fmtDate(conversation.next_follow_up_at),
                follow_up_step: conversation.follow_up_step,
                handoff_reason: conversation.handoff_reason,
              }}
            />
          </Card>
        </div>
      </div>

      <Modal
        title="Send meeting link"
        open={linkOpen}
        onClose={() => setLinkOpen(false)}
        footer={
          <>
            <button type="button" className="btn" onClick={() => setLinkOpen(false)}>
              Cancel
            </button>
            <button type="button" className="btn btn-primary" onClick={saveMeetingLink} disabled={busy === "link"}>
              {busy === "link" ? "Saving…" : "Save link"}
            </button>
          </>
        }
      >
        <Field label="Meeting URL *">
          <input
            className="input"
            value={meetingUrl}
            onChange={(event) => setMeetingUrl(event.target.value)}
            placeholder="https://calendly.com/…"
          />
        </Field>
        <Field label="Notes">
          <textarea
            className="textarea"
            value={meetingNotes}
            onChange={(event) => setMeetingNotes(event.target.value)}
          />
        </Field>
      </Modal>

      <Modal
        title="Add internal note"
        open={noteOpen}
        onClose={() => setNoteOpen(false)}
        footer={
          <>
            <button type="button" className="btn" onClick={() => setNoteOpen(false)}>
              Cancel
            </button>
            <button type="button" className="btn btn-primary" onClick={saveNote} disabled={busy === "note"}>
              {busy === "note" ? "Saving…" : "Add note"}
            </button>
          </>
        }
      >
        <Field label="Note">
          <textarea className="textarea" value={note} onChange={(event) => setNote(event.target.value)} />
        </Field>
      </Modal>
    </div>
  );
}

export default ConversationDetailClient;
