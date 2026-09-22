"use client";

import { FormEvent, KeyboardEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Bold, Code, Italic, LoaderCircle, Pencil, Plus, Strikethrough, Trash2 } from "lucide-react";
import { Alert } from "@/components/ui";
import { WhatsAppMarkup } from "@/components/whatsapp-preview";
import { api, ApiError, messageFrom } from "@/lib/api";
import { useT } from "@/lib/i18n";
import { CONTACT_EXAMPLES, CONTACT_VARIABLES, type ContactValues } from "@/lib/contact-variables";
import type { CannedResponse } from "@/types";

export type CannedVars = ContactValues;

// The contact variables, plus `my_name` kept as an alias so replies saved
// before the rename keep resolving.
const CANNED_TOKENS = new RegExp(`\\{(${[...CONTACT_VARIABLES, "my_name"].join("|")})\\}`, "g");

/** Fill the placeholders a saved reply may carry; unknown values stay visible
 * so the operator notices and edits before sending. */
export function renderCanned(content: string, vars: CannedVars): string {
  return content.replace(CANNED_TOKENS, (whole, key) => (key === "my_name" ? vars.agent_name : vars[key as keyof CannedVars]) || whole);
}

const VARIABLES = CONTACT_VARIABLES.map((name) => `{${name}}`);
const SHOWN = 8;

/** Saved replies for the composer: typing "/" opens a picker filtered by what
 * follows and Enter inserts the rendered reply. The list is managed from
 * Settings (CannedRepliesView). */
export function useCannedReplies({ slug, vars, onInsert }: { slug: string; vars: CannedVars; onInsert: (text: string) => void }) {
  const t = useT();
  const [items, setItems] = useState<CannedResponse[]>([]);
  const [query, setQuery] = useState<string | null>(null);
  const [index, setIndex] = useState(0);

  const load = useCallback(() => api<CannedResponse[]>(`/portal/${slug}/canned-responses`).then(setItems).catch(() => {}), [slug]);
  useEffect(() => { load(); }, [load]);

  const matches = useMemo(() => {
    if (query === null) return [];
    const q = query.toLowerCase();
    return items.filter((item) => !q || item.shortcut.toLowerCase().includes(q) || item.content.toLowerCase().includes(q)).slice(0, SHOWN);
  }, [items, query]);

  function pick(item: CannedResponse) {
    onInsert(renderCanned(item.content, vars));
    setQuery(null);
  }

  const onChange = useCallback((value: string) => {
    setQuery(value.startsWith("/") ? value.slice(1) : null);
    setIndex(0);
  }, []);

  const reset = useCallback(() => { setQuery(null); setIndex(0); }, []);

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (query === null) return;
    if (event.key === "Escape") { setQuery(null); return; }
    if (!matches.length) return;
    if (event.key === "ArrowDown") { event.preventDefault(); setIndex((i) => (i + 1) % matches.length); }
    else if (event.key === "ArrowUp") { event.preventDefault(); setIndex((i) => (i - 1 + matches.length) % matches.length); }
    else if (event.key === "Enter" || event.key === "Tab") { event.preventDefault(); pick(matches[Math.min(index, matches.length - 1)]); }
  }

  const popup = query !== null ? (
    <div className="canned-popup">
      {matches.length ? matches.map((item, i) => (
        <button type="button" key={item.id} className={i === index ? "active" : ""} onMouseDown={(e) => { e.preventDefault(); pick(item); }} onMouseEnter={() => setIndex(i)}>
          <strong>/{item.shortcut}</strong>
          <small>{renderCanned(item.content, vars)}</small>
        </button>
      )) : <p className="muted">{items.length ? t("portal.canned.noMatches") : t("portal.canned.empty")}</p>}
    </div>
  ) : null;

  return { popup, onChange, onKeyDown, reset };
}


/** The saved replies of the business, from Settings: list, create, edit, delete. */
export function CannedRepliesView({ slug, canManage }: { slug: string; canManage: boolean }) {
  const t = useT();
  const [items, setItems] = useState<CannedResponse[]>([]);
  const [editing, setEditing] = useState<CannedResponse | "new" | null>(null);
  const [content, setContent] = useState("");
  const [confirmId, setConfirmId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const contentRef = useRef<HTMLTextAreaElement>(null);

  const load = useCallback(() => api<CannedResponse[]>(`/portal/${slug}/canned-responses`).then(setItems).catch((err) => setError(messageFrom(err))), [slug]);
  useEffect(() => { load(); }, [load]);
  // Load the body being edited, or clear it for a new reply.
  useEffect(() => { setContent(editing && editing !== "new" ? editing.content : ""); }, [editing]);

  function insertVariable(token: string) {
    const el = contentRef.current;
    const at = el ? el.selectionStart : content.length;
    setContent(content.slice(0, at) + token + content.slice(at));
    requestAnimationFrame(() => { if (el) { el.focus(); const caret = at + token.length; el.setSelectionRange(caret, caret); } });
  }

  // Wrap the selection in WhatsApp's markers, or drop a pair for the caret.
  function wrap(mark: string) {
    const el = contentRef.current;
    if (!el) return;
    const [start, end] = [el.selectionStart, el.selectionEnd];
    setContent(content.slice(0, start) + mark + content.slice(start, end) + mark + content.slice(end));
    requestAnimationFrame(() => { el.focus(); el.setSelectionRange(start + mark.length, end + mark.length); });
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!editing) return;
    const data = new FormData(event.currentTarget);
    const body = { shortcut: String(data.get("shortcut") || "").trim().toLowerCase(), content: content.trim() };
    setBusy(true); setError("");
    try {
      if (editing === "new") await api<CannedResponse>(`/portal/${slug}/canned-responses`, { method: "POST", body: JSON.stringify(body) });
      else await api<CannedResponse>(`/portal/${slug}/canned-responses/${editing.id}`, { method: "PATCH", body: JSON.stringify(body) });
      setEditing(null);
      await load();
    } catch (err) {
      setError(err instanceof ApiError && err.status === 409 ? t("portal.canned.duplicate") : messageFrom(err));
    } finally { setBusy(false); }
  }

  async function remove(item: CannedResponse) {
    setBusy(true); setError("");
    try {
      await api(`/portal/${slug}/canned-responses/${item.id}`, { method: "DELETE" });
      setConfirmId(null);
      await load();
    } catch (err) { setError(messageFrom(err)); } finally { setBusy(false); }
  }

  return <section className="form-section">
    <div className="section-copy"><h2>{t("portal.canned.manageTitle")}</h2><p>{t("portal.canned.manageDescription")}</p></div>
    <div className="form-fields">
      {editing ? (
        <form className="modal-form canned-editor" onSubmit={save}>
          <label>{t("portal.canned.form.shortcut")}
            <div className="canned-shortcut-field"><span>/</span><input name="shortcut" required pattern="[a-z0-9_-]+" maxLength={60} defaultValue={editing === "new" ? "" : editing.shortcut} placeholder="saludo" autoFocus /></div>
            <span className="field-help">{t("portal.canned.form.shortcutHelp")}</span>
          </label>
          <label>{t("portal.canned.form.content")}
            <textarea ref={contentRef} rows={4} required maxLength={4000} value={content} onChange={(e) => setContent(e.target.value)} placeholder={t("portal.canned.form.contentPlaceholder")} />
          </label>
          <div className="template-toolbar">
            <button type="button" className="icon-button" title={t("portal.templates.form.bold")} aria-label={t("portal.templates.form.bold")} onClick={() => wrap("*")}><Bold size={14} /></button>
            <button type="button" className="icon-button" title={t("portal.templates.form.italic")} aria-label={t("portal.templates.form.italic")} onClick={() => wrap("_")}><Italic size={14} /></button>
            <button type="button" className="icon-button" title={t("portal.templates.form.strike")} aria-label={t("portal.templates.form.strike")} onClick={() => wrap("~")}><Strikethrough size={14} /></button>
            <button type="button" className="icon-button" title={t("portal.templates.form.mono")} aria-label={t("portal.templates.form.mono")} onClick={() => wrap("```")}><Code size={14} /></button>
          </div>
          <div className="canned-vars">{VARIABLES.map((v) => <button type="button" key={v} onClick={() => insertVariable(v)}>{v}</button>)}</div>
          <span className="field-help">{t("portal.canned.form.variablesHint")}</span>
          {content.trim() && <div className="canned-preview"><span>{t("portal.canned.form.preview")}</span><p><WhatsAppMarkup text={renderCanned(content, CONTACT_EXAMPLES)} /></p></div>}
          {error && <Alert>{error}</Alert>}
          <div className="modal-actions">
            <button type="button" className="button" onClick={() => { setEditing(null); setError(""); }}>{t("portal.contacts.form.cancel")}</button>
            <button className="button primary" disabled={busy}>{busy ? <LoaderCircle className="spin" size={16} /> : t("portal.canned.form.save")}</button>
          </div>
        </form>
      ) : (
        <>
          {error && <Alert>{error}</Alert>}
          <div className="canned-manage-list">
            {items.map((item) => (
              <div key={item.id} className="canned-manage-row">
                <div><strong>/{item.shortcut}</strong><small>{item.content}</small></div>
                {canManage && (confirmId === item.id ? (
                  <div className="canned-row-actions">
                    <button type="button" className="button danger small" disabled={busy} onClick={() => remove(item)}>{busy ? <LoaderCircle className="spin" size={14} /> : t("portal.canned.deleteConfirm")}</button>
                    <button type="button" className="button small" onClick={() => setConfirmId(null)}>{t("portal.contacts.form.cancel")}</button>
                  </div>
                ) : (
                  <div className="canned-row-actions">
                    <button type="button" className="icon-button" title={t("portal.canned.edit")} aria-label={t("portal.canned.edit")} onClick={() => { setError(""); setEditing(item); }}><Pencil size={15} /></button>
                    <button type="button" className="icon-button danger" title={t("portal.canned.delete")} aria-label={t("portal.canned.delete")} onClick={() => setConfirmId(item.id)}><Trash2 size={15} /></button>
                  </div>
                ))}
              </div>
            ))}
            {!items.length && <p className="muted">{t("portal.canned.empty")}</p>}
          </div>
          {canManage && <button type="button" className="button primary align-start" onClick={() => { setError(""); setEditing("new"); }}><Plus size={15} /> {t("portal.canned.new")}</button>}
        </>
      )}
    </div>
  </section>;
}
