"use client";

import { Plus } from "lucide-react";

export type AccountRowState = "connected" | "pending" | "disconnected";
export type AccountRow = { id: string; title: string; inboxName: string; agentName: string; state: AccountRowState; stateLabel: string };

/** A client's accounts on one channel, one row each: the number or handle
 * with the name the Inbox shows under it, who answers, the state, and the
 * way in. The channel page shows this until an account is picked. */
export function AccountList({ rows, summary, addLabel, openLabel, onOpen, onAdd }: {
  rows: AccountRow[]; summary: string; addLabel: string; openLabel: string;
  onOpen: (id: string) => void; onAdd: () => void;
}) {
  return <section className="account-list">
    <div className="account-list-head"><p>{summary}</p><button type="button" className="button secondary" onClick={onAdd}><Plus size={15} /> {addLabel}</button></div>
    <ul className="channel-accounts">{rows.map((row) => <li key={row.id}>
      <i className={`channel-state-dot ${row.state}`} aria-hidden="true" />
      <span className="account-id"><strong>{row.title}</strong><small>{row.inboxName}</small></span>
      <span className="account-agent">{row.agentName}</span>
      <span className={`account-state ${row.state}`}>{row.stateLabel}</span>
      <button type="button" className="button secondary" onClick={() => onOpen(row.id)}>{openLabel}</button>
    </li>)}</ul>
  </section>;
}
