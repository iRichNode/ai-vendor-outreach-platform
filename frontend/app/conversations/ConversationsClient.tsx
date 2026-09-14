"use client";

import Link from "next/link";
import { useState } from "react";

import {
  Card,
  EmptyState,
  ErrorNote,
  PageHeader,
  Spinner,
  StatusBadge,
  TableShell,
} from "@/components/ui";
import { api } from "@/lib/api";
import { CONVERSATION_STATUSES } from "@/lib/constants";
import { fmtDate, fmtNumber, truncate } from "@/lib/format";
import { useApi } from "@/lib/useApi";

const PAGE_SIZE = 25;

export function ConversationsClient() {
  const [search, setSearch] = useState("");
  const [term, setTerm] = useState("");
  const [status, setStatus] = useState("");
  const [offset, setOffset] = useState(0);

  const conversations = useApi(
    () =>
      api.conversations.list({
        search: term || undefined,
        status: status || undefined,
        limit: PAGE_SIZE,
        offset,
      }),
    [term, status, offset],
  );

  const items: any[] = conversations.data?.items ?? [];
  const total = Number(conversations.data?.total ?? items.length);
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div>
      <PageHeader
        title="Conversations"
        subtitle={`${fmtNumber(total)} conversation thread(s)`}
        actions={
          <Link className="btn btn-sm" href="/queue">
            Queue
          </Link>
        }
      />

      <Card>
        <form
          className="mb-4 flex flex-wrap items-end gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            setOffset(0);
            setTerm(search.trim());
          }}
        >
          <div className="min-w-[14rem] flex-1">
            <span className="label">Search</span>
            <input
              className="input"
              placeholder="Company or subject"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
          </div>
          <div className="w-52">
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
              {CONVERSATION_STATUSES.map((value) => (
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
              setTerm("");
              setStatus("");
              setOffset(0);
            }}
          >
            Reset
          </button>
        </form>

        <ErrorNote message={conversations.error} />
        {conversations.loading && !conversations.data ? <Spinner label="Loading conversations…" /> : null}
        {conversations.data && items.length === 0 ? (
          <EmptyState message="No conversations yet." hint="Threads appear after the first reply." />
        ) : null}

        {items.length > 0 ? (
          <TableShell>
            <thead>
              <tr>
                <th>Company</th>
                <th>Subject</th>
                <th>Status</th>
                <th>Flags</th>
                <th>Messages</th>
                <th>Last inbound</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {items.map((conversation) => (
                <tr key={conversation.id}>
                  <td className="text-slate-100">
                    {conversation.company || "—"}
                    <p className="muted text-xs">{conversation.contact_name || ""}</p>
                  </td>
                  <td>{truncate(conversation.subject || "—", 46)}</td>
                  <td>
                    <StatusBadge status={conversation.status} />
                  </td>
                  <td>
                    <div className="flex flex-wrap gap-1">
                      {conversation.ai_paused ? <span className="badge badge-amber">ai paused</span> : null}
                      {conversation.human_controlled ? (
                        <span className="badge badge-indigo">human</span>
                      ) : null}
                      {conversation.archived ? <span className="badge badge-slate">archived</span> : null}
                    </div>
                  </td>
                  <td className="mono">{fmtNumber(conversation.message_count ?? 0)}</td>
                  <td className="muted text-xs">{fmtDate(conversation.last_inbound_at)}</td>
                  <td>
                    <Link className="btn btn-sm btn-primary" href={`/conversations/${conversation.id}`}>
                      Open
                    </Link>
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
  );
}

export default ConversationsClient;
