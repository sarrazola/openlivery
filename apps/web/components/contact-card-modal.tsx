"use client";

import { FormEvent, useEffect, useState } from "react";
import { LoaderCircle, Pencil } from "lucide-react";
import { Alert, Modal } from "@/components/ui";
import { PhoneInput } from "@/components/phone-input";
import { api, ApiError, messageFrom } from "@/lib/api";
import { formatPhone } from "@/lib/dial-codes";
import { useLanguage } from "@/lib/i18n";
import { tagStyle } from "@/lib/tags";
import type { Contact, ContactField } from "@/types";

/** The contact's card from inside a conversation: who they are, their
 * custom details, tags and notes, editable in place, without leaving the
 * inbox for the Contacts view. Saves through the same portal route the
 * Contacts view uses. */
export function ContactCardModal({ slug, contactId, onClose, onSaved }: { slug: string; contactId: string; onClose: () => void; onSaved: (contact: Contact) => void }) {
  const { t, lang } = useLanguage();
  const [contact, setContact] = useState<Contact | null>(null);
  const [fields, setFields] = useState<ContactField[]>([]);
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let alive = true;
    Promise.all([
      api<Contact>(`/portal/${slug}/contacts/${contactId}`),
      api<ContactField[]>(`/portal/${slug}/contact-fields`).catch(() => [] as ContactField[]),
    ]).then(([row, defs]) => { if (alive) { setContact(row); setFields(defs.filter((field) => !field.builtin)); } })
      .catch((err) => { if (alive) setError(messageFrom(err)); });
    return () => { alive = false; };
  }, [slug, contactId]);

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!contact) return;
    const data = new FormData(event.currentTarget);
    const body = {
      name: String(data.get("name") || "").trim(),
      phone: String(data.get("phone") || "").trim(),
      email: String(data.get("email") || "").trim() || null,
      notes: String(data.get("notes") || "").trim(),
      attributes: Object.fromEntries(fields.map((field) => [field.key, String(data.get(`attr:${field.key}`) || "").trim()])),
    };
    setBusy(true); setError("");
    try {
      const saved = await api<Contact>(`/portal/${slug}/contacts/${contact.id}`, { method: "PATCH", body: JSON.stringify(body) });
      setContact(saved);
      setEditing(false);
      onSaved(saved);
    } catch (err) {
      setError(err instanceof ApiError && err.status === 409 ? t("portal.contacts.form.duplicatePhone") : messageFrom(err));
    } finally { setBusy(false); }
  }

  const title = contact ? (contact.name.trim() || formatPhone(contact.phone) || t("portal.contacts.unnamed")) : t("portal.inbox.conversation.contactCard");
  const details = fields.filter((field) => contact?.attributes?.[field.key]);
  return <Modal open title={title} description={contact ? [formatPhone(contact.phone), contact.email].filter(Boolean).join(" · ") || undefined : undefined} onClose={onClose}>
    {!contact && !error && <div className="modal-form"><LoaderCircle className="spin" size={18} /></div>}
    {error && !contact && <div className="modal-form"><Alert>{error}</Alert></div>}
    {contact && !editing && <div className="modal-form contact-card">
      <section>
        <h4>{t("portal.contacts.tags.heading")}</h4>
        {contact.tags?.length ? <div className="tag-chips">{contact.tags.map((tag) => <span key={tag.id} className="tag-chip" style={tagStyle(tag.color)}>{tag.name}</span>)}</div> : <p className="muted">{t("portal.inbox.conversation.contactNoTags")}</p>}
      </section>
      {fields.length > 0 && <section>
        <h4>{t("portal.contacts.fields.heading")}</h4>
        {details.length ? <dl className="contact-card-details">{details.map((field) => <div key={field.key}><dt>{field.label}</dt><dd>{contact.attributes?.[field.key]}</dd></div>)}</dl> : <p className="muted">{t("portal.contacts.fields.empty")}</p>}
      </section>}
      <section>
        <h4>{t("portal.contacts.notes")}</h4>
        {contact.notes ? <p className="contact-card-notes">{contact.notes}</p> : <p className="muted">{t("portal.contacts.noNotes")}</p>}
      </section>
      <div className="modal-actions">
        <button type="button" className="button" onClick={onClose}>{t("portal.inbox.conversation.contactCardClose")}</button>
        <button type="button" className="button primary" onClick={() => setEditing(true)}><Pencil size={15} /> {t("portal.contacts.edit")}</button>
      </div>
    </div>}
    {contact && editing && <form className="modal-form" onSubmit={save}>
      <div className="form-grid">
        <label>{t("portal.contacts.form.name")}<input name="name" defaultValue={contact.name} placeholder={t("portal.contacts.form.namePlaceholder")} autoFocus /></label>
        <label>{t("portal.contacts.form.phone")}<PhoneInput name="phone" initial={contact.phone} locale={lang} required placeholder="300 123 4567" searchPlaceholder={t("portal.contacts.form.searchCountry")} /><span className="field-help">{t("portal.contacts.form.phoneHelp")}</span></label>
      </div>
      <label>{t("portal.contacts.form.email")}<input name="email" type="email" defaultValue={contact.email ?? ""} placeholder="name@company.com" /></label>
      {fields.length > 0 && <div className="form-grid">
        {fields.map((field) => <label key={field.key}>{field.label}<input name={`attr:${field.key}`} type={field.kind === "number" ? "number" : field.kind === "email" ? "email" : field.kind === "phone" ? "tel" : "text"} step={field.kind === "number" ? "any" : undefined} maxLength={500} defaultValue={contact.attributes?.[field.key] ?? ""} placeholder={field.description || undefined} /></label>)}
      </div>}
      <label>{t("portal.contacts.form.notes")}<textarea name="notes" rows={4} defaultValue={contact.notes} placeholder={t("portal.contacts.form.notesPlaceholder")} /></label>
      {error && <Alert>{error}</Alert>}
      <div className="modal-actions"><button type="button" className="button" onClick={() => setEditing(false)}>{t("portal.contacts.form.cancel")}</button><button className="button primary" disabled={busy}>{busy ? <LoaderCircle className="spin" size={16} /> : t("portal.contacts.form.save")}</button></div>
    </form>}
  </Modal>;
}
