"use client";

import { useState } from "react";
import { Pencil, Trash2 } from "lucide-react";
import { ConfirmModal } from "@/components/confirm-modal";
import { useT } from "@/lib/i18n";

type KeyToggle = {
  checked: boolean;
  label: string;
  hint: string;
  /** What the dialog says before turning the key on or off. */
  confirm: (on: boolean) => { title: string; message: string; label: string };
  onChange: (on: boolean) => Promise<void> | void;
};

// Replace and remove for a stored credential, as two quiet icon buttons beside
// its status line; the labels ride as tooltips. Removing asks first. A key that
// can be paused gets its on/off switch in the same row, which also asks first
// and says what turning it on or off does.
export function KeyActions({ busy, replaceLabel, removeLabel, confirmTitle, confirmMessage, toggle, onReplace, onRemove }: {
  busy: boolean;
  replaceLabel: string;
  removeLabel: string;
  confirmTitle: string;
  confirmMessage?: string;
  toggle?: KeyToggle;
  onReplace: () => void;
  onRemove: () => Promise<void> | void;
}) {
  const t = useT();
  const [confirming, setConfirming] = useState(false);
  const [switching, setSwitching] = useState<boolean | null>(null);
  const switchCopy = toggle && switching !== null ? toggle.confirm(switching) : null;
  return <div className="key-configured-actions">
    {toggle && <label className="switch-row key-switch" title={`${toggle.label}. ${toggle.hint}`}><input type="checkbox" aria-label={toggle.label} checked={toggle.checked} disabled={busy} onChange={(e) => setSwitching(e.target.checked)} /></label>}
    <button type="button" className="icon-button" disabled={busy} title={replaceLabel} aria-label={replaceLabel} onClick={onReplace}><Pencil size={15} /></button>
    <button type="button" className="icon-button key-remove" disabled={busy} title={removeLabel} aria-label={removeLabel} onClick={() => setConfirming(true)}><Trash2 size={15} /></button>
    {confirming && <ConfirmModal title={confirmTitle} message={confirmMessage} confirmLabel={removeLabel} cancelLabel={t("common.cancel")} confirmIcon={<Trash2 size={15} />} onConfirm={onRemove} onClose={() => setConfirming(false)} />}
    {toggle && switchCopy && switching !== null && <ConfirmModal title={switchCopy.title} message={switchCopy.message} confirmLabel={switchCopy.label} cancelLabel={t("common.cancel")} danger={false} onConfirm={() => toggle.onChange(switching)} onClose={() => setSwitching(null)} />}
  </div>;
}
