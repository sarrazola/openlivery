"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { CheckCircle2, Inbox, LoaderCircle, Merge, MessageSquarePlus, Pencil, Plus, Search, Trash2, UserRound } from "lucide-react";
import { TemplatePicker } from "./templates";
import { Alert, EmptyState, Modal } from "@/components/ui";
import { PhoneInput } from "@/components/phone-input";
import { formatPhone } from "@/lib/dial-codes";
import { api, ApiError, messageFrom } from "@/lib/api";
import { formatWhen } from "@/lib/datetime";
import { useLanguage, useT } from "@/lib/i18n";
import type { Contact, Conversation, PortalChannel } from "@/types";

const LIMIT = 50;

export function ContactsView({ slug, channels, openConversation }: { slug: string; channels: PortalChannel[]; openConversation: (conversation: Conversation) => void }) {
  const t = useT();
  const { lang } = useLanguage();
  const [items, setItems] = useState<Contact[]>([]);
  const [selected, setSelected] = useState<Contact | null>(null);
  const [history, setHistory] = useState<Conversation[]>([]);
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [editing, setEditing] = useState<"new" | "edit" | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [typed, setTyped] = useState("");
  const [merging, setMerging] = useState(false);
  const [mergeQuery, setMergeQuery] = useState("");
  const [mergePrimary, setMergePrimary] = useState<Contact | null>(null);
  const cloudLine = channels.find((c) => c.channel === "whatsapp_cloud");
  const qrLine = channels.find((c) => c.channel === "whatsapp");
  const [starting, setStarting] = useState<"whatsapp_cloud" | "whatsapp" | null>(null);
  async function startWithTemplate(payload: { name: string; language: string; variables: string[] }) {
    if (!selected) return;
    const conv = await api<Conversation>(`/portal/${slug}/contacts/${selected.id}/conversations`, { method: "POST", body: JSON.stringify({ channel: "whatsapp_cloud", template: payload }) });
    openConversation(conv);
  }
  async function startWithText(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected) return;
    const text = String(new FormData(event.currentTarget).get("text") || "").trim();
    setBusy(true); setError("");
    try {
      const conv = await api<Conversation>(`/portal/${slug}/contacts/${selected.id}/conversations`, { method: "POST", body: JSON.stringify({ channel: "whatsapp", text }) });
      setStarting(null);
      openConversation(conv);
    } catch (err) { setError(messageFrom(err)); } finally { setBusy(false); }
  }
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const id = setTimeout(() => setQuery(search.trim()), 300);
    return () => clearTimeout(id);
  }, [search]);

  const load = useCallback(async () => {
    const params = new URLSearchParams({ limit: String(LIMIT) });
    if (query) params.set("search", query);
    const rows = await api<Contact[]>(`/portal/${slug}/contacts?${params}`);
    setItems(rows);
    return rows;
  }, [slug, query]);

  useEffect(() => {
    setLoading(true);
    load().catch((err) => setError(messageFrom(err))).finally(() => setLoading(false));
  }, [load]);

  const choose = useCallback(async (contact: Contact) => {
    setSelected(contact);
    setHistory(await api<Conversation[]>(`/portal/${slug}/contacts/${contact.id}/conversations`));
  }, [slug]);

  const phoneLabel = (phone: string | null) => formatPhone(phone);
  const nameOf = (contact: Contact) => contact.name.trim() || phoneLabel(contact.phone) || t("portal.contacts.unnamed");

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const body = {
      name: String(data.get("name") || "").trim(),
      phone: String(data.get("phone") || "").trim(),
      email: String(data.get("email") || "").trim() || null,
      notes: String(data.get("notes") || "").trim(),
    };
    setBusy(true); setError("");
    try {
      const saved = editing === "new"
        ? await api<Contact>(`/portal/${slug}/contacts`, { method: "POST", body: JSON.stringify(body) })
        : await api<Contact>(`/portal/${slug}/contacts/${selected!.id}`, { method: "PATCH", body: JSON.stringify(body) });
      setEditing(null);
      await load();
      await choose(saved);
    } catch (err) {
      setError(err instanceof ApiError && err.status === 409 ? t("portal.contacts.form.duplicatePhone") : messageFrom(err));
    } finally { setBusy(false); }
  }

  async function merge(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected || !mergePrimary) return;
    setBusy(true); setError("");
    try {
      const primary = await api<Contact>(`/portal/${slug}/contacts/${selected.id}/merge`, {
        method: "POST",
        body: JSON.stringify({ primary_contact_id: mergePrimary.id }),
      });
      setMerging(false); setMergePrimary(null); setMergeQuery("");
      await load();
      await choose(primary);
    } catch (err) { setError(messageFrom(err)); } finally { setBusy(false); }
  }

  const confirmWord = t("portal.contacts.deleteWord");
  const confirmed = typed.trim().toUpperCase() === confirmWord.toUpperCase();
  async function remove(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected || !confirmed) return;
    setBusy(true); setError("");
    try {
      await api(`/portal/${slug}/contacts/${selected.id}`, { method: "DELETE" });
      setDeleting(false); setTyped("");
      setSelected(null); setHistory([]);
      await load();
    } catch (err) { setError(messageFrom(err)); } finally { setBusy(false); }
  }

  return <>
    <div className="portal-contacts">
      <aside>
        <div className="inbox-search"><Search size={16} /><input value={search} onChange={(e) => setSearch(e.target.value)} placeholder={t("portal.contacts.searchPlaceholder")} /></div>
        <div className="portal-contacts-toolbar">
          <span>{t("portal.contacts.count", { count: items.length })}</span>
          <button className="button primary small" onClick={() => setEditing("new")}><Plus size={15} /> {t("portal.contacts.new")}</button>
        </div>
        {loading ? <div className="no-conversations"><LoaderCircle className="spin" size={16} /></div>
          : items.map((contact) => <button key={contact.id} onClick={() => choose(contact)} className={selected?.id === contact.id ? "active" : ""}>
            <span className="entity-avatar tiny"><UserRound size={15} /></span>
            <span>
              <span className="portal-inbox-row-top"><strong>{nameOf(contact)}</strong>{contact.last_activity_at && <time>{formatWhen(contact.last_activity_at, lang)}</time>}</span>
              <small className="portal-inbox-preview">{phoneLabel(contact.phone)}{contact.email ? ` · ${contact.email}` : ""}</small>
              <small className="inbox-row-meta">{t("portal.contacts.conversationCount", { count: contact.conversation_count })}{contact.open_count > 0 && <span className="mini-badge human">{t("portal.contacts.openCount", { count: contact.open_count })}</span>}</small>
            </span>
          </button>)}
        {!loading && !items.length && <div className="no-conversations">{query ? t("portal.contacts.noMatches") : t("portal.contacts.empty")}</div>}
      </aside>
      <section>
        {selected ? <>
          <header>
            <div>
              <strong>{nameOf(selected)}</strong>
              <small className="portal-channel-line">{phoneLabel(selected.phone)}{selected.email ? ` · ${selected.email}` : ""}</small>
            </div>
            <div className="thread-actions">
              {(cloudLine || qrLine) && selected.phone && <button className="button primary small" onClick={() => setStarting(cloudLine ? "whatsapp_cloud" : "whatsapp")}><MessageSquarePlus size={15} /> {t("portal.contacts.startConversation")}</button>}
              <button className="button small" onClick={() => setEditing("edit")}><Pencil size={15} /> {t("portal.contacts.edit")}</button>
              <button className="button small" onClick={() => { setMergePrimary(null); setMergeQuery(""); setMerging(true); }}><Merge size={15} /> {t("portal.contacts.merge")}</button>
              <button className="icon-button danger" onClick={() => { setTyped(""); setDeleting(true); }} disabled={busy} title={t("portal.contacts.delete")} aria-label={t("portal.contacts.delete")}><Trash2 size={16} /></button>
            </div>
          </header>
          {error && <Alert>{error}</Alert>}
          <div className="portal-contact-body">
            <section className="portal-contact-notes">
              <h3>{t("portal.contacts.notes")}</h3>
              {selected.notes ? <p>{selected.notes}</p> : <p className="muted">{t("portal.contacts.noNotes")}</p>}
            </section>
            <section>
              <h3>{t("portal.contacts.history")}</h3>
              {history.length ? <div className="portal-contact-history">{history.map((conv) => <button key={conv.id} onClick={() => openConversation(conv)}>
                <span className={`mini-badge ${conv.status === "resolved" ? "resolved" : conv.mode}`}>{conv.status === "resolved" ? <><CheckCircle2 size={11} /> {t("portal.inbox.conversation.resolvedBadge")}</> : conv.mode === "human" ? t("portal.inbox.list.humanSupport") : t("portal.inbox.list.aiAgent")}</span>
                <span className="portal-contact-history-text"><strong>{formatWhen(conv.created_at, lang)}</strong><small>{conv.preview || t("portal.inbox.list.noMessages")}</small></span>
                <Inbox size={15} />
              </button>)}</div> : <p className="muted">{t("portal.contacts.noHistory")}</p>}
            </section>
          </div>
        </> : <EmptyState icon={<UserRound />} title={t("portal.contacts.selectTitle")} description={t("portal.contacts.selectDescription")} />}
      </section>
    </div>
    <TemplatePicker slug={slug} open={starting === "whatsapp_cloud" && Boolean(selected)} title={t("portal.contacts.startTitle", { name: selected ? nameOf(selected) : "" })} onClose={() => setStarting(null)} onSend={startWithTemplate} />
    <Modal open={starting === "whatsapp" && Boolean(selected)} title={t("portal.contacts.startQrTitle", { name: selected ? nameOf(selected) : "" })} description={t("portal.contacts.startQrDescription")} onClose={() => setStarting(null)}>
      <form className="modal-form" onSubmit={startWithText}>
        <label>{t("portal.contacts.startMessage")}<textarea name="text" rows={4} required autoFocus /></label>
        {error && <Alert>{error}</Alert>}
        <div className="modal-actions"><button type="button" className="button" onClick={() => setStarting(null)}>{t("portal.contacts.form.cancel")}</button><button className="button primary" disabled={busy}>{busy ? <LoaderCircle className="spin" size={16} /> : t("portal.contacts.startSend")}</button></div>
      </form>
    </Modal>
    <Modal open={deleting && Boolean(selected)} title={t("portal.contacts.deleteTitle", { name: selected ? nameOf(selected) : "" })} onClose={() => setDeleting(false)}>
      <form className="modal-form" onSubmit={remove}>
        <Alert type="error">{t("portal.contacts.deleteWarning", { count: selected?.conversation_count ?? 0 })}</Alert>
        <div className="confirm-word"><span>{t("portal.contacts.deleteTypeWord")}</span><code>{confirmWord}</code></div>
        <input aria-label={confirmWord} value={typed} onChange={(e) => setTyped(e.target.value)} placeholder={confirmWord} autoFocus autoComplete="off" spellCheck={false} />
        {error && <Alert>{error}</Alert>}
        <div className="modal-actions"><button type="button" className="button" onClick={() => setDeleting(false)}>{t("portal.contacts.form.cancel")}</button><button className="button danger" disabled={!confirmed || busy}>{busy ? <LoaderCircle className="spin" size={16} /> : <><Trash2 size={15} /> {t("portal.contacts.deleteConfirm")}</>}</button></div>
      </form>
    </Modal>
    <Modal open={merging && Boolean(selected)} title={t("portal.contacts.mergeTitle", { name: selected ? nameOf(selected) : "" })} description={t("portal.contacts.mergeDescription")} onClose={() => setMerging(false)}>
      <form className="modal-form" onSubmit={merge}>
        <label>{t("portal.contacts.mergePrimaryLabel")}<input value={mergeQuery} onChange={(e) => setMergeQuery(e.target.value)} placeholder={t("portal.contacts.searchPlaceholder")} autoFocus /></label>
        <div className="merge-candidates">
          {items
            .filter((contact) => contact.id !== selected?.id)
            .filter((contact) => !mergeQuery.trim() || `${contact.name} ${contact.phone ?? ""} ${contact.email ?? ""}`.toLowerCase().includes(mergeQuery.trim().toLowerCase()))
            .slice(0, 8)
            .map((contact) => <button type="button" key={contact.id} className={mergePrimary?.id === contact.id ? "active" : ""} onClick={() => setMergePrimary(contact)}>
              <span className="entity-avatar tiny"><UserRound size={15} /></span>
              <span><strong>{nameOf(contact)}</strong><small>{phoneLabel(contact.phone)}{contact.email ? ` · ${contact.email}` : ""}</small></span>
              {mergePrimary?.id === contact.id && <CheckCircle2 size={16} />}
            </button>)}
          {items.filter((contact) => contact.id !== selected?.id).length === 0 && <p className="muted">{t("portal.contacts.mergeNoCandidates")}</p>}
        </div>
        {mergePrimary && <Alert type="error">{t("portal.contacts.mergeWarning", { merged: selected ? nameOf(selected) : "", primary: nameOf(mergePrimary) })}</Alert>}
        {error && <Alert>{error}</Alert>}
        <div className="modal-actions"><button type="button" className="button" onClick={() => setMerging(false)}>{t("portal.contacts.form.cancel")}</button><button className="button primary" disabled={!mergePrimary || busy}>{busy ? <LoaderCircle className="spin" size={16} /> : <><Merge size={15} /> {t("portal.contacts.mergeConfirm")}</>}</button></div>
      </form>
    </Modal>
    <Modal open={editing !== null} title={editing === "new" ? t("portal.contacts.newTitle") : t("portal.contacts.editTitle")} onClose={() => setEditing(null)}>
      <form className="modal-form" onSubmit={save}>
        <div className="form-grid">
          <label>{t("portal.contacts.form.name")}<input name="name" defaultValue={editing === "edit" ? selected?.name : ""} placeholder={t("portal.contacts.form.namePlaceholder")} autoFocus /></label>
          <label>{t("portal.contacts.form.phone")}<PhoneInput key={editing === "edit" ? selected?.id : "new"} name="phone" initial={editing === "edit" ? selected?.phone : ""} locale={lang} required placeholder="300 123 4567" searchPlaceholder={t("portal.contacts.form.searchCountry")} /><span className="field-help">{t("portal.contacts.form.phoneHelp")}</span></label>
        </div>
        <label>{t("portal.contacts.form.email")}<input name="email" type="email" defaultValue={editing === "edit" ? selected?.email ?? "" : ""} placeholder="name@company.com" /></label>
        <label>{t("portal.contacts.form.notes")}<textarea name="notes" rows={4} defaultValue={editing === "edit" ? selected?.notes : ""} placeholder={t("portal.contacts.form.notesPlaceholder")} /></label>
        {error && <Alert>{error}</Alert>}
        <div className="modal-actions"><button type="button" className="button" onClick={() => setEditing(null)}>{t("portal.contacts.form.cancel")}</button><button className="button primary" disabled={busy}>{busy ? <LoaderCircle className="spin" size={16} /> : t("portal.contacts.form.save")}</button></div>
      </form>
    </Modal>
  </>;
}
