"use client";

import { useState } from "react";
import { Pencil, Trash2 } from "lucide-react";
import { ConfirmModal } from "@/components/confirm-modal";
import { useT } from "@/lib/i18n";

// Replace and remove for a stored credential, as two quiet icon buttons beside
// its status line; the labels ride as tooltips. Removing asks first.
export function KeyActions({ busy, replaceLabel, removeLabel, confirmTitle, confirmMessage, onReplace, onRemove }: {
  busy: boolean;
  replaceLabel: string;
  removeLabel: string;
  confirmTitle: string;
  confirmMessage?: string;
  onReplace: () => void;
  onRemove: () => Promise<void> | void;
}) {
  const t = useT();
  const [confirming, setConfirming] = useState(false);
  return <div className="key-configured-actions">
    <button type="button" className="icon-button" disabled={busy} title={replaceLabel} aria-label={replaceLabel} onClick={onReplace}><Pencil size={15} /></button>
    <button type="button" className="icon-button key-remove" disabled={busy} title={removeLabel} aria-label={removeLabel} onClick={() => setConfirming(true)}><Trash2 size={15} /></button>
    {confirming && <ConfirmModal title={confirmTitle} message={confirmMessage} confirmLabel={removeLabel} cancelLabel={t("common.cancel")} confirmIcon={<Trash2 size={15} />} onConfirm={onRemove} onClose={() => setConfirming(false)} />}
  </div>;
}
