"use client";

import { Plus } from "lucide-react";

export type LineState = "connected" | "pending" | "disconnected" | "off";
export type LineOption = { id: string; name: string; state: LineState };

/** Pills for a client's accounts on one channel, plus one to add another.
 * Rendered only once the client has at least one, so the first connection
 * looks exactly like a single-account setup. */
export function LineSwitcher({ lines, selectedId, adding, addLabel, newLabel, onSelect, onAdd }: {
  lines: LineOption[]; selectedId: string | null; adding: boolean; addLabel: string; newLabel: string;
  onSelect: (id: string) => void; onAdd: () => void;
}) {
  if (!lines.length) return null;
  return <div className="line-switcher" role="tablist">
    {lines.map((line) => <button type="button" key={line.id} role="tab" aria-selected={!adding && line.id === selectedId} className={!adding && line.id === selectedId ? "active" : ""} onClick={() => onSelect(line.id)}><i className={`channel-state-dot ${line.state}`} aria-hidden="true" />{line.name}</button>)}
    {adding
      ? <button type="button" role="tab" aria-selected className="active add"><Plus size={14} /> {newLabel}</button>
      : <button type="button" className="add" onClick={onAdd}><Plus size={14} /> {addLabel}</button>}
  </div>;
}
