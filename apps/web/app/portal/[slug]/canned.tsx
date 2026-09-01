"use client";

import { FormEvent, KeyboardEvent, useCallback, useEffect, useMemo, useState } from "react";
import { LoaderCircle, Pencil, Plus, Trash2, Zap } from "lucide-react";
import { Alert, Modal } from "@/components/ui";
import { api, ApiError, messageFrom } from "@/lib/api";
import { useT } from "@/lib/i18n";
import type { CannedResponse } from "@/types";

export type CannedVars = { contact_name: string; contact_phone: string; my_name: string; business_name: string };

/** Fill the placeholders a saved reply may carry; unknown values stay visible
 * so the operator notices and edits before sending. */
export function renderCanned(content: string, vars: CannedVars): string {
  return content.replace(/\{(contact_name|contact_phone|my_name|business_name)\}/g, (whole, key) => vars[key as keyof CannedVars] || whole);
}

const VARIABLES = ["{contact_name}", "{contact_phone}", "{my_name}", "{business_name}"] as const;
const SHOWN = 8;

/** Saved replies for the composer: typing "/" opens a picker filtered by what
 * follows, Enter inserts the rendered reply, and a modal manages the list. */
export function useCannedReplies({ slug, vars, onInsert }: { slug: string; vars: CannedVars; onInsert: (text: string) => void }) {
  const t = useT();
  const [items, setItems] = useState<CannedResponse[]>([]);
  const [query, setQuery] = useState<string | null>(null);
  const [index, setIndex] = useState(0);
  const [managing, setManaging] = useState(false);
  const [editing, setEditing] = useState<CannedResponse | "new" | null>(null);
  const [confirmId, setConfirmId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

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

  function onKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (query === null) return;
    if (event.key === "Escape") { setQuery(null); return; }
    if (!matches.length) return;
    if (event.key === "ArrowDown") { event.preventDefault(); setIndex((i) => (i + 1) % matches.length); }
    else if (event.key === "ArrowUp") { event.preventDefault(); setIndex((i) => (i - 1 + matches.length) % matches.length); }
    else if (event.key === "Enter" || event.key === "Tab") { event.preventDefault(); pick(matches[Math.min(index, matches.length - 1)]); }
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!editing) return;
    const data = new FormData(event.currentTarget);
    const body = { shortcut: String(data.get("shortcut") || "").trim().toLowerCase(), content: String(data.get("content") || "").trim() };
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

  const popup = query !== null ? (
    <div className="canned-popup">
      {matches.length ? matches.map((item, i) => (
        <button type="button" key={item.id} className={i === index ? "active" : ""} onMouseDown={(e) => { e.preventDefault(); pick(item); }} onMouseEnter={() => setIndex(i)}>
          <strong>/{item.shortcut}</strong>
          <small>{renderCanned(item.content, vars)}</small>
        </button>
      )) : <p className="muted">{items.length ? t("portal.canned.noMatches") : t("portal.canned.empty")}</p>}
      <footer>
        <button type="button" onMouseDown={(e) => { e.preventDefault(); setQuery(null); setEditing(null); setConfirmId(null); setError(""); setManaging(true); }}>
          <Zap size={13} /> {t("portal.canned.manage")}
        </button>
      </footer>
    </div>
  ) : null;

  const manager = (
    <Modal
      open={managing}
      title={t("portal.canned.manageTitle")}
      description={t("portal.canned.manageDescription")}
      onClose={() => { setManaging(false); setEditing(null); setConfirmId(null); setError(""); }}
    >
      {editing ? (
        <form className="modal-form" onSubmit={save}>
          <label>{t("portal.canned.form.shortcut")}
            <div className="canned-shortcut-field"><span>/</span><input name="shortcut" required pattern="[a-z0-9_-]+" maxLength={60} defaultValue={editing === "new" ? "" : editing.shortcut} placeholder="saludo" autoFocus /></div>
            <span className="field-help">{t("portal.canned.form.shortcutHelp")}</span>
          </label>
          <label>{t("portal.canned.form.content")}
            <textarea name="content" rows={4} required maxLength={4000} defaultValue={editing === "new" ? "" : editing.content} placeholder={t("portal.canned.form.contentPlaceholder")} />
            <span className="field-help">{t("portal.canned.form.variablesHint")}</span>
          </label>
          <div className="canned-vars">{VARIABLES.map((v) => <code key={v}>{v}</code>)}</div>
          {error && <Alert>{error}</Alert>}
          <div className="modal-actions">
            <button type="button" className="button" onClick={() => { setEditing(null); setError(""); }}>{t("portal.contacts.form.cancel")}</button>
            <button className="button primary" disabled={busy}>{busy ? <LoaderCircle className="spin" size={16} /> : t("portal.canned.form.save")}</button>
          </div>
        </form>
      ) : (
        <div className="modal-form">
          {error && <Alert>{error}</Alert>}
          <div className="canned-manage-list">
            {items.map((item) => (
              <div key={item.id} className="canned-manage-row">
                <div><strong>/{item.shortcut}</strong><small>{item.content}</small></div>
                {confirmId === item.id ? (
                  <div className="canned-row-actions">
                    <button type="button" className="button danger small" disabled={busy} onClick={() => remove(item)}>{busy ? <LoaderCircle className="spin" size={14} /> : t("portal.canned.deleteConfirm")}</button>
                    <button type="button" className="button small" onClick={() => setConfirmId(null)}>{t("portal.contacts.form.cancel")}</button>
                  </div>
                ) : (
                  <div className="canned-row-actions">
                    <button type="button" className="icon-button" title={t("portal.canned.edit")} aria-label={t("portal.canned.edit")} onClick={() => { setError(""); setEditing(item); }}><Pencil size={15} /></button>
                    <button type="button" className="icon-button danger" title={t("portal.canned.delete")} aria-label={t("portal.canned.delete")} onClick={() => setConfirmId(item.id)}><Trash2 size={15} /></button>
                  </div>
                )}
              </div>
            ))}
            {!items.length && <p className="muted">{t("portal.canned.empty")}</p>}
          </div>
          <div className="modal-actions">
            <button type="button" className="button primary" onClick={() => { setError(""); setEditing("new"); }}><Plus size={15} /> {t("portal.canned.new")}</button>
          </div>
        </div>
      )}
    </Modal>
  );

  return { popup, manager, onChange, onKeyDown, reset, openManager: () => setManaging(true) };
}
