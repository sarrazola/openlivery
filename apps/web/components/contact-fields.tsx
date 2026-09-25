"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { LoaderCircle, Plus, Trash2 } from "lucide-react";
import { Alert } from "@/components/ui";
import { api, messageFrom } from "@/lib/api";
import { useT } from "@/lib/i18n";
import type { ContactField, ContactFieldKind } from "@/types";

const KINDS: ContactFieldKind[] = ["text", "number", "email", "phone"];
const KEY_RE = /^[a-z][a-z0-9_]{1,59}$/;

/** The client's custom contact fields: what a contact can hold beyond name,
 * phone and email. Defined once here; every agent of the client can then ask
 * for them and the portal shows them on the contact. `base` is the
 * collection URL. */
export function ContactFieldsView({ base }: { base: string }) {
  const t = useT();
  const [fields, setFields] = useState<ContactField[]>([]);
  const [deleting, setDeleting] = useState<ContactField | null>(null);
  const [draft, setDraft] = useState({ key: "", label: "", kind: "text" as ContactFieldKind, description: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try { setFields(await api<ContactField[]>(base)); } catch (err) { setError(messageFrom(err)); }
  }, [base]);
  useEffect(() => { load(); }, [load]);

  const kindLabel = (kind: ContactFieldKind) => t(`clients.fields.kind_${kind}`);
  const labelOf = (field: { key: string; label: string; builtin: boolean }) =>
    field.builtin && (field.key === "name" || field.key === "email" || field.key === "phone") ? t(`agents.capture.builtin_${field.key}`) : field.label;
  const custom = fields.filter((field) => !field.builtin);
  const builtins = fields.filter((field) => field.builtin);

  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const key = draft.key.trim();
    const label = draft.label.trim();
    if (!KEY_RE.test(key) || !label) return;
    setBusy(true); setError("");
    try {
      await api<ContactField>(base, { method: "POST", body: JSON.stringify({ key, label, kind: draft.kind, description: draft.description.trim() }) });
      setDraft({ key: "", label: "", kind: "text", description: "" });
      await load();
    } catch (err) { setError(messageFrom(err)); } finally { setBusy(false); }
  }
  async function update(field: ContactField, patch: Partial<Pick<ContactField, "label" | "kind" | "description">>) {
    if (!field.id) return;
    setError("");
    try { await api<ContactField>(`${base}/${field.id}`, { method: "PATCH", body: JSON.stringify(patch) }); await load(); }
    catch (err) { setError(messageFrom(err)); }
  }
  async function remove(field: ContactField) {
    if (!field.id) return;
    setBusy(true); setError("");
    try { await api(`${base}/${field.id}`, { method: "DELETE" }); setDeleting(null); await load(); }
    catch (err) { setError(messageFrom(err)); } finally { setBusy(false); }
  }

  return <section className="form-section">
    <div className="section-copy"><h2>{t("clients.fields.title")}</h2><p>{t("clients.fields.intro")}</p></div>
    <div className="form-fields contact-fields">
      <div className="contact-fields-builtin">
        {builtins.map((field) => <span key={field.key} className="pill" title={field.key}>{labelOf(field)} <code>{field.key}</code></span>)}
        <small className="muted">{t("clients.fields.builtinHint")}</small>
      </div>
      {!custom.length && <p className="muted">{t("clients.fields.empty")}</p>}
      {custom.map((field) => deleting?.id === field.id
        ? <div key={field.key} className="tag-manage-confirm"><span>{t("clients.fields.deleteConfirm", { label: field.label })}</span><span className="tag-manage-confirm-actions"><button type="button" className="button small" onClick={() => setDeleting(null)}>{t("common.cancel")}</button><button type="button" className="button danger small" disabled={busy} onClick={() => remove(field)}>{t("clients.fields.deleteAction")}</button></span></div>
        : <div key={field.key} className="contact-field-row">
          <div className="contact-field-main">
            <input defaultValue={field.label} maxLength={80} aria-label={t("clients.fields.labelLabel")} onBlur={(e) => { const label = e.target.value.trim(); if (label && label !== field.label) update(field, { label }); }} onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }} />
            <code>{field.key}</code>
            <select value={field.kind} aria-label={t("clients.fields.kindLabel")} onChange={(e) => update(field, { kind: e.target.value as ContactFieldKind })}>{KINDS.map((kind) => <option key={kind} value={kind}>{kindLabel(kind)}</option>)}</select>
            <button type="button" className="icon-button danger" onClick={() => setDeleting(field)} title={t("clients.fields.deleteAction")} aria-label={t("clients.fields.deleteAction")}><Trash2 size={15} /></button>
          </div>
          <input defaultValue={field.description} maxLength={1000} placeholder={t("clients.fields.descriptionPlaceholder")} aria-label={t("clients.fields.descriptionLabel")} onBlur={(e) => { const description = e.target.value.trim(); if (description !== field.description) update(field, { description }); }} onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }} />
        </div>)}
      <form className="contact-field-new" onSubmit={create}>
        <div className="form-grid">
          <label>{t("clients.fields.labelLabel")}<input value={draft.label} maxLength={80} onChange={(e) => setDraft((d) => ({ ...d, label: e.target.value, key: d.key || e.target.value.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "").slice(0, 60) }))} placeholder={t("clients.fields.labelPlaceholder")} /></label>
          <label>{t("clients.fields.keyLabel")}<input value={draft.key} maxLength={60} onChange={(e) => setDraft((d) => ({ ...d, key: e.target.value }))} placeholder={t("clients.fields.keyPlaceholder")} /><span className="field-help">{t("clients.fields.keyHelp")}</span></label>
        </div>
        <div className="form-grid">
          <label>{t("clients.fields.kindLabel")}<select value={draft.kind} onChange={(e) => setDraft((d) => ({ ...d, kind: e.target.value as ContactFieldKind }))}>{KINDS.map((kind) => <option key={kind} value={kind}>{kindLabel(kind)}</option>)}</select></label>
          <label>{t("clients.fields.descriptionLabel")}<input value={draft.description} maxLength={1000} onChange={(e) => setDraft((d) => ({ ...d, description: e.target.value }))} placeholder={t("clients.fields.descriptionPlaceholder")} /><span className="field-help">{t("clients.fields.descriptionHelp")}</span></label>
        </div>
        <div><button className="button primary small" disabled={busy || !draft.label.trim() || !KEY_RE.test(draft.key.trim())}>{busy ? <LoaderCircle className="spin" size={14} /> : <Plus size={14} />} {t("clients.fields.create")}</button></div>
      </form>
      {error && <Alert>{error}</Alert>}
    </div>
  </section>;
}
