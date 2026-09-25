"use client";

import { useCallback, useEffect, useState } from "react";
import { Pencil, Plus, Trash2 } from "lucide-react";
import { Alert } from "@/components/ui";
import { ConfirmModal } from "@/components/confirm-modal";
import { ContactFieldModal } from "@/components/contact-field-modal";
import { api, messageFrom } from "@/lib/api";
import { useT } from "@/lib/i18n";
import type { ContactField, ContactFieldKind } from "@/types";

/** The client's custom contact fields: what a contact can hold beyond name,
 * phone and email. Defined once here; every agent of the client can then ask
 * for them and the portal shows them on the contact. `base` is the
 * collection URL. */
export function ContactFieldsView({ base }: { base: string }) {
  const t = useT();
  const [fields, setFields] = useState<ContactField[]>([]);
  const [editing, setEditing] = useState<ContactField | null | "new">(null);
  const [deleting, setDeleting] = useState<ContactField | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try { setFields(await api<ContactField[]>(base)); } catch (err) { setError(messageFrom(err)); }
  }, [base]);
  useEffect(() => { load(); }, [load]);

  const kindLabel = (kind: ContactFieldKind) => t(`clients.fields.kind_${kind}`);
  const builtinLabel = (field: ContactField) =>
    field.key === "name" || field.key === "email" || field.key === "phone" ? t(`agents.capture.builtin_${field.key}`) : field.label;
  const custom = fields.filter((field) => !field.builtin);
  const builtins = fields.filter((field) => field.builtin);

  async function remove(field: ContactField) {
    if (!field.id) return;
    await api(`${base}/${field.id}`, { method: "DELETE" });
    setDeleting(null);
    await load();
  }

  return <section className="form-section">
    <div className="section-copy"><h2>{t("clients.fields.title")}</h2><p>{t("clients.fields.intro")}</p></div>
    <div className="form-fields contact-fields">
      <div className="contact-fields-builtin">
        {builtins.map((field) => <span key={field.key} className="pill" title={field.key}>{builtinLabel(field)}</span>)}
        <small className="muted">{t("clients.fields.builtinHint")}</small>
      </div>
      {custom.map((field) => <div key={field.key} className="contact-field-row">
        <div className="contact-field-main">
          <div className="contact-field-text">
            <strong>{field.label} <span className="pill">{kindLabel(field.kind)}</span></strong>
            <small>{field.description || t("clients.fields.noDescription")}</small>
            <small className="muted">{t("clients.fields.contactCount", { count: field.contact_count ?? 0 })}</small>
          </div>
          <span className="escalation-actions">
            <button type="button" className="icon-button" onClick={() => setEditing(field)} title={t("clients.fields.edit")} aria-label={t("clients.fields.edit")}><Pencil size={15} /></button>
            <button type="button" className="icon-button danger" onClick={() => setDeleting(field)} title={t("clients.fields.deleteAction")} aria-label={t("clients.fields.deleteAction")}><Trash2 size={15} /></button>
          </span>
        </div>
      </div>)}
      {!custom.length && <p className="esc-empty">{t("clients.fields.empty")}</p>}
      <div><button type="button" className="button secondary small" onClick={() => setEditing("new")}><Plus size={14} /> {t("clients.fields.newField")}</button></div>
      {error && <Alert>{error}</Alert>}
    </div>
    {editing !== null && <ContactFieldModal base={base} field={editing === "new" ? null : editing} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); load(); }} />}
    {deleting && <ConfirmModal
      title={t("clients.fields.deleteTitle", { label: deleting.label })}
      message={(deleting.contact_count ?? 0) > 0 ? t("clients.fields.deleteWithValues", { count: deleting.contact_count ?? 0 }) : t("clients.fields.deleteNoValues")}
      confirmLabel={t("clients.fields.deleteAction")}
      cancelLabel={t("common.cancel")}
      confirmIcon={<Trash2 size={15} />}
      onConfirm={() => remove(deleting)}
      onClose={() => setDeleting(null)}
    />}
  </section>;
}
