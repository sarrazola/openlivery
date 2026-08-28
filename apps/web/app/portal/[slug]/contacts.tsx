"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { CheckCircle2, Inbox, LoaderCircle, Pencil, Plus, Search, Trash2, UserRound } from "lucide-react";
import { Alert, EmptyState, Modal } from "@/components/ui";
import { api, messageFrom } from "@/lib/api";
import { formatWhen } from "@/lib/datetime";
import { useLanguage, useT } from "@/lib/i18n";
import type { Contact, Conversation } from "@/types";

const LIMIT = 50;

export function ContactsView({ slug, openConversation }: { slug: string; openConversation: (conversation: Conversation) => void }) {
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

  const phoneLabel = (phone: string | null) => (phone ? `+${phone}` : "");
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
    } catch (err) { setError(messageFrom(err)); } finally { setBusy(false); }
  }

  const confirmWord = selected ? nameOf(selected) : "";
  const confirmed = typed.trim().toLowerCase() === confirmWord.trim().toLowerCase();
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
              <button className="button small" onClick={() => setEditing("edit")}><Pencil size={15} /> {t("portal.contacts.edit")}</button>
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
    <Modal open={deleting && Boolean(selected)} title={t("portal.contacts.deleteTitle", { name: confirmWord })} onClose={() => setDeleting(false)}>
      <form className="modal-form" onSubmit={remove}>
        <Alert type="error">{t("portal.contacts.deleteWarning", { count: selected?.conversation_count ?? 0 })}</Alert>
        <label>{t("portal.contacts.deleteTypeName", { name: confirmWord })}<input value={typed} onChange={(e) => setTyped(e.target.value)} placeholder={confirmWord} autoFocus autoComplete="off" /></label>
        {error && <Alert>{error}</Alert>}
        <div className="modal-actions"><button type="button" className="button" onClick={() => setDeleting(false)}>{t("portal.contacts.form.cancel")}</button><button className="button danger" disabled={!confirmed || busy}>{busy ? <LoaderCircle className="spin" size={16} /> : <><Trash2 size={15} /> {t("portal.contacts.deleteConfirm")}</>}</button></div>
      </form>
    </Modal>
    <Modal open={editing !== null} title={editing === "new" ? t("portal.contacts.newTitle") : t("portal.contacts.editTitle")} onClose={() => setEditing(null)}>
      <form className="modal-form" onSubmit={save}>
        <div className="form-grid">
          <label>{t("portal.contacts.form.name")}<input name="name" defaultValue={editing === "edit" ? selected?.name : ""} placeholder={t("portal.contacts.form.namePlaceholder")} autoFocus /></label>
          <label>{t("portal.contacts.form.phone")}<input name="phone" required defaultValue={editing === "edit" ? phoneLabel(selected?.phone ?? null) : ""} placeholder="+57 300 123 4567" /><span className="field-help">{t("portal.contacts.form.phoneHelp")}</span></label>
        </div>
        <label>{t("portal.contacts.form.email")}<input name="email" type="email" defaultValue={editing === "edit" ? selected?.email ?? "" : ""} placeholder="name@company.com" /></label>
        <label>{t("portal.contacts.form.notes")}<textarea name="notes" rows={4} defaultValue={editing === "edit" ? selected?.notes : ""} placeholder={t("portal.contacts.form.notesPlaceholder")} /></label>
        {error && <Alert>{error}</Alert>}
        <div className="modal-actions"><button type="button" className="button" onClick={() => setEditing(null)}>{t("portal.contacts.form.cancel")}</button><button className="button primary" disabled={busy}>{busy ? <LoaderCircle className="spin" size={16} /> : t("portal.contacts.form.save")}</button></div>
      </form>
    </Modal>
  </>;
}
