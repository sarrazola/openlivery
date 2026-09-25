"use client";

import { FormEvent, useState } from "react";
import { LoaderCircle } from "lucide-react";
import { Alert, Modal } from "@/components/ui";
import { api, messageFrom } from "@/lib/api";
import { useT } from "@/lib/i18n";
import type { ContactField, ContactFieldKind } from "@/types";

const KINDS: ContactFieldKind[] = ["text", "number", "email", "phone"];
const KEY_RE = /^[a-z][a-z0-9_]{1,59}$/;

/** The key the agent and the API use, derived from the name people see:
 * "Presupuesto estimado" becomes "presupuesto_estimado". */
export function keyFromLabel(label: string): string {
  return label.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "").replace(/^[0-9]+/, "").slice(0, 60);
}

/** Create or edit one of the client's custom contact fields: type, name and
 * the description that tells the agent what the value is and when it
 * applies. The key is derived from the name and fixed once created. */
export function ContactFieldModal({ base, field, onClose, onSaved }: { base: string; field: ContactField | null; onClose: () => void; onSaved: (field: ContactField) => void }) {
  const t = useT();
  const [kind, setKind] = useState<ContactFieldKind>(field?.kind ?? "text");
  const [label, setLabel] = useState(field?.label ?? "");
  const [description, setDescription] = useState(field?.description ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const key = field ? field.key : keyFromLabel(label);
  const kindLabel = (value: ContactFieldKind) => t(`clients.fields.kind_${value}`);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!label.trim() || (!field && !KEY_RE.test(key))) return;
    setBusy(true); setError("");
    try {
      const saved = field?.id
        ? await api<ContactField>(`${base}/${field.id}`, { method: "PATCH", body: JSON.stringify({ label: label.trim(), kind, description: description.trim() }) })
        : await api<ContactField>(base, { method: "POST", body: JSON.stringify({ key, label: label.trim(), kind, description: description.trim() }) });
      onSaved(saved);
    } catch (err) { setError(messageFrom(err)); } finally { setBusy(false); }
  }

  return <Modal open title={field ? t("clients.fields.editTitle") : t("clients.fields.newTitle")} description={t("clients.fields.modalCopy")} onClose={onClose}>
    <form className="modal-form" onSubmit={submit}>
      <label>{t("clients.fields.kindLabel")}<select value={kind} onChange={(e) => setKind(e.target.value as ContactFieldKind)}>{KINDS.map((value) => <option key={value} value={value}>{kindLabel(value)}</option>)}</select><span className="field-help">{t("clients.fields.kindHelp")}</span></label>
      <label>{t("clients.fields.nameLabel")}<input value={label} maxLength={80} onChange={(e) => setLabel(e.target.value)} placeholder={t("clients.fields.namePlaceholder")} autoFocus required />
        {key && <span className="field-help">{field ? t("clients.fields.keyFixed", { key }) : t("clients.fields.keyPreview", { key })}</span>}
      </label>
      <label>{t("clients.fields.descriptionLabel")}<textarea value={description} rows={3} maxLength={1000} onChange={(e) => setDescription(e.target.value)} placeholder={t("clients.fields.descriptionPlaceholder")} /><span className="field-help">{t("clients.fields.descriptionHelp")}</span></label>
      {error && <Alert>{error}</Alert>}
      <div className="modal-actions">
        <button type="button" className="button" onClick={onClose}>{t("common.cancel")}</button>
        <button className="button primary" disabled={busy || !label.trim() || (!field && !KEY_RE.test(key))}>{busy ? <LoaderCircle className="spin" size={16} /> : field ? t("clients.fields.saveChanges") : t("clients.fields.create")}</button>
      </div>
    </form>
  </Modal>;
}
