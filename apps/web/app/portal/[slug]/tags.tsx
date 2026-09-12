"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { Trash2 } from "lucide-react";
import { Alert } from "@/components/ui";
import { api, messageFrom } from "@/lib/api";
import { useT } from "@/lib/i18n";
import { TAG_PALETTE, tagColor, tagStyle } from "@/lib/tags";
import type { ContactTag } from "@/types";

/** The client's tag catalog, from Settings: rename, recolor, delete, create.
 * Putting a tag on a contact happens on the contact card. */
export function TagsView({ slug, canManage }: { slug: string; canManage: boolean }) {
  const t = useT();
  const [tags, setTags] = useState<ContactTag[]>([]);
  const [deleting, setDeleting] = useState<ContactTag | null>(null);
  const [name, setName] = useState("");
  // Which tag has its color menu open.
  const [picking, setPicking] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try { setTags(await api<ContactTag[]>(`/portal/${slug}/tags`)); } catch (err) { setError(messageFrom(err)); }
  }, [slug]);
  useEffect(() => { load(); }, [load]);

  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) return;
    setBusy(true); setError("");
    try { await api<ContactTag>(`/portal/${slug}/tags`, { method: "POST", body: JSON.stringify({ name: trimmed }) }); setName(""); await load(); }
    catch (err) { setError(messageFrom(err)); } finally { setBusy(false); }
  }
  async function update(tag: ContactTag, patch: { name?: string; color?: string }) {
    if (patch.name !== undefined && (!patch.name.trim() || patch.name.trim() === tag.name)) return;
    setError("");
    try { await api<ContactTag>(`/portal/${slug}/tags/${tag.id}`, { method: "PATCH", body: JSON.stringify(patch) }); await load(); }
    catch (err) { setError(messageFrom(err)); }
  }
  async function remove(tag: ContactTag) {
    setBusy(true); setError("");
    try { await api(`/portal/${slug}/tags/${tag.id}`, { method: "DELETE" }); setDeleting(null); await load(); }
    catch (err) { setError(messageFrom(err)); } finally { setBusy(false); }
  }

  return <section className="form-section">
    <div className="section-copy"><h2>{t("portal.contacts.tags.manageTitle")}</h2><p>{t("portal.contacts.tags.manageIntro")}</p></div>
    <div className="form-fields tag-manage">
      {!tags.length && <p className="muted">{t("portal.contacts.tags.noTags")}</p>}
      {tags.map((tag) => deleting?.id === tag.id
        ? <div key={tag.id} className="tag-manage-confirm"><span>{t("portal.contacts.tags.deleteConfirm", { name: tag.name, count: tag.contact_count })}</span><span className="tag-manage-confirm-actions"><button type="button" className="button small" onClick={() => setDeleting(null)}>{t("portal.contacts.form.cancel")}</button><button type="button" className="button danger small" disabled={busy} onClick={() => remove(tag)}>{t("portal.contacts.tags.deleteAction")}</button></span></div>
        : <div key={tag.id} className="tag-manage-row">
          <div className="tag-color-pick">
            <button type="button" className="tag-color-current" style={tagStyle(tag.color)} disabled={!canManage} aria-haspopup="menu" aria-expanded={picking === tag.id} aria-label={t("portal.contacts.tags.pickColor")} title={t("portal.contacts.tags.pickColor")} onClick={() => setPicking(picking === tag.id ? null : tag.id)} />
            {picking === tag.id && <>
              <div className="menu-backdrop" onClick={() => setPicking(null)} />
              <div className="tag-color-menu" role="menu">
                <div className="tag-swatches" role="radiogroup" aria-label={tag.name}>
                  {TAG_PALETTE.map(({ value, name: label }) => <button type="button" key={value} style={tagStyle(value)} className={value === tagColor(tag.color) ? "active" : ""} role="radio" aria-checked={value === tagColor(tag.color)} aria-label={label} title={label} onClick={() => { update(tag, { color: value }); setPicking(null); }} />)}
                </div>
                <label className="tag-swatch-custom" style={tagStyle(tag.color)} title={t("portal.contacts.tags.customColor")}><input type="color" value={tagColor(tag.color)} aria-label={t("portal.contacts.tags.customColor")} onChange={(e) => update(tag, { color: e.target.value })} /></label>
              </div>
            </>}
          </div>
          <input defaultValue={tag.name} maxLength={40} readOnly={!canManage} onBlur={(e) => canManage && update(tag, { name: e.target.value })} onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }} />
          {(tag.route_assignee_name || tag.route_team_name) && <span className="tag-route-note">{t("portal.contacts.tags.routedTo", { team: tag.route_assignee_name ?? tag.route_team_name ?? "" })}</span>}
          <small>{t("portal.contacts.tags.count", { count: tag.contact_count })}</small>
          {canManage && <button type="button" className="icon-button danger" onClick={() => setDeleting(tag)} title={t("portal.contacts.tags.deleteAction")} aria-label={t("portal.contacts.tags.deleteAction")}><Trash2 size={15} /></button>}
        </div>)}
      {canManage && <form className="tag-manage-new" onSubmit={create}>
        <input value={name} onChange={(e) => setName(e.target.value)} maxLength={40} placeholder={t("portal.contacts.tags.newPlaceholder")} />
        <button className="button primary small" disabled={busy || !name.trim()}>{t("portal.contacts.tags.newAction")}</button>
      </form>}
      {error && <Alert>{error}</Alert>}
    </div>
  </section>;
}
