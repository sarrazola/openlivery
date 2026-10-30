"use client";

import { Pencil, Trash2 } from "lucide-react";

// Replace and remove for a stored credential, as two quiet icon buttons beside
// its status line; the labels ride as tooltips.
export function KeyActions({ busy, replaceLabel, removeLabel, onReplace, onRemove }: { busy: boolean; replaceLabel: string; removeLabel: string; onReplace: () => void; onRemove: () => void }) {
  return <div className="key-configured-actions">
    <button type="button" className="icon-button" disabled={busy} title={replaceLabel} aria-label={replaceLabel} onClick={onReplace}><Pencil size={15} /></button>
    <button type="button" className="icon-button key-remove" disabled={busy} title={removeLabel} aria-label={removeLabel} onClick={onRemove}><Trash2 size={15} /></button>
  </div>;
}
