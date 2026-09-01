"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { CheckCircle2, Clock, LoaderCircle, Plus, Search, Trash2, XCircle } from "lucide-react";
import { Alert, EmptyState, Modal } from "@/components/ui";
import { api, messageFrom } from "@/lib/api";
import { useT } from "@/lib/i18n";
import type { Template } from "@/types";

export function variableCount(body: string): number {
  const found = Array.from(body.matchAll(/\{\{(\d+)\}\}/g)).map((m) => Number(m[1]));
  return found.length ? Math.max(...found) : 0;
}

export function renderTemplate(body: string, values: string[]): string {
  return body.replace(/\{\{(\d+)\}\}/g, (whole, n) => values[Number(n) - 1] || whole);
}

export function TemplatesView({ slug, supported }: { slug: string; supported: boolean }) {
  const t = useT();
  const [items, setItems] = useState<Template[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [creating, setCreating] = useState(false);
  const [busy, setBusy] = useState(false);
  const [body, setBody] = useState("");
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [removing, setRemoving] = useState<Template | null>(null);
  const count = variableCount(body);
  const categories = useMemo(() => Array.from(new Set(items.map((i) => i.category))).sort(), [items]);
  const shown = useMemo(() => {
    const query = search.trim().toLowerCase();
    return items.filter((item) => {
      if (query && !`${item.name} ${item.body} ${item.language}`.toLowerCase().includes(query)) return false;
      if (categoryFilter && item.category !== categoryFilter) return false;
      if (statusFilter === "PENDING") return item.status !== "APPROVED" && item.status !== "REJECTED";
      if (statusFilter) return item.status === statusFilter;
      return true;
    });
  }, [items, search, statusFilter, categoryFilter]);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try { setItems(await api<Template[]>(`/portal/${slug}/templates`)); }
    catch (err) { setError(messageFrom(err)); }
    finally { setLoading(false); }
  }, [slug]);
  useEffect(() => { if (supported) load(); else setLoading(false); }, [load, supported]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const examples = Array.from({ length: count }, (_, i) => String(data.get(`example${i + 1}`) || "").trim());
    setBusy(true); setError("");
    try {
      await api<Template>(`/portal/${slug}/templates`, { method: "POST", body: JSON.stringify({
        name: String(data.get("name") || "").trim().toLowerCase(),
        language: String(data.get("language") || "es").trim(),
        category: String(data.get("category") || "UTILITY"),
        body: body.trim(),
        footer: String(data.get("footer") || "").trim(),
        examples,
      }) });
      setCreating(false); setBody("");
      await load();
    } catch (err) { setError(messageFrom(err)); } finally { setBusy(false); }
  }

  async function remove(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!removing) return;
    setBusy(true); setError("");
    try {
      const query = removing.id ? `?hsm_id=${encodeURIComponent(removing.id)}` : "";
      await api(`/portal/${slug}/templates/${encodeURIComponent(removing.name)}${query}`, { method: "DELETE" });
      setRemoving(null);
      await load();
    } catch (err) { setError(messageFrom(err)); } finally { setBusy(false); }
  }

  const statusBadge = (status: string) => {
    if (status === "APPROVED") return <span className="mini-badge resolved"><CheckCircle2 size={11} /> {t("portal.templates.status.approved")}</span>;
    if (status === "REJECTED") return <span className="mini-badge rejected"><XCircle size={11} /> {t("portal.templates.status.rejected")}</span>;
    return <span className="mini-badge pending"><Clock size={11} /> {t("portal.templates.status.pending")}</span>;
  };

  if (!supported) return <EmptyState icon={<Clock />} title={t("portal.templates.unsupportedTitle")} description={t("portal.templates.unsupportedDescription")} />;

  return <>
    <div className="portal-templates">
      <div className="portal-templates-toolbar">
        <p>{t("portal.templates.intro")}</p>
        <button className="button primary small" onClick={() => setCreating(true)}><Plus size={15} /> {t("portal.templates.new")}</button>
      </div>
      {error && !creating && !removing && <Alert>{error}</Alert>}
      {loading ? <div className="no-conversations"><LoaderCircle className="spin" size={16} /></div>
        : items.length ? <>
          <div className="portal-templates-filters">
            <div className="template-search"><Search size={15} /><input value={search} onChange={(e) => setSearch(e.target.value)} placeholder={t("portal.templates.searchPlaceholder")} /></div>
            <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} aria-label={t("portal.templates.table.status")}>
              <option value="">{t("portal.templates.filterStatusAll")}</option>
              <option value="APPROVED">{t("portal.templates.status.approved")}</option>
              <option value="PENDING">{t("portal.templates.status.pending")}</option>
              <option value="REJECTED">{t("portal.templates.status.rejected")}</option>
            </select>
            <select value={categoryFilter} onChange={(e) => setCategoryFilter(e.target.value)} aria-label={t("portal.templates.table.category")}>
              <option value="">{t("portal.templates.filterCategoryAll")}</option>
              {categories.map((category) => <option key={category} value={category}>{category.toLowerCase()}</option>)}
            </select>
          </div>
          {shown.length ? <div className="table-shell">
            <table className="data-table portal-template-table">
              <thead><tr>
                <th>{t("portal.templates.table.name")}</th>
                <th>{t("portal.templates.table.language")}</th>
                <th>{t("portal.templates.table.category")}</th>
                <th>{t("portal.templates.table.status")}</th>
                <th />
              </tr></thead>
              <tbody>{shown.map((item) => <tr key={`${item.name}-${item.language}`}>
                <td className="portal-template-name">
                  <strong>{item.name}</strong>
                  <small>{item.body}</small>
                  {item.status === "REJECTED" && item.rejected_reason && <small className="danger">{item.rejected_reason}</small>}
                </td>
                <td>{item.language}</td>
                <td>{item.category.toLowerCase()}</td>
                <td>{statusBadge(item.status)}</td>
                <td className="portal-template-actions"><button className="icon-button danger" onClick={() => setRemoving(item)} title={t("portal.templates.delete")} aria-label={t("portal.templates.delete")}><Trash2 size={15} /></button></td>
              </tr>)}</tbody>
            </table>
          </div> : <div className="no-conversations">{t("portal.templates.noMatches")}</div>}
        </>
        : <EmptyState icon={<Clock />} title={t("portal.templates.emptyTitle")} description={t("portal.templates.emptyDescription")} />}
    </div>
    <Modal open={Boolean(removing)} title={t("portal.templates.deleteTitle", { name: removing?.name ?? "" })} onClose={() => setRemoving(null)}>
      <form className="modal-form" onSubmit={remove}>
        <Alert type="error">{t("portal.templates.deleteWarning")}</Alert>
        {error && <Alert>{error}</Alert>}
        <div className="modal-actions"><button type="button" className="button" onClick={() => setRemoving(null)}>{t("portal.contacts.form.cancel")}</button><button className="button danger" disabled={busy}>{busy ? <LoaderCircle className="spin" size={16} /> : <><Trash2 size={15} /> {t("portal.templates.deleteConfirm")}</>}</button></div>
      </form>
    </Modal>
    <Modal open={creating} title={t("portal.templates.newTitle")} description={t("portal.templates.newDescription")} onClose={() => setCreating(false)}>
      <form className="modal-form" onSubmit={submit}>
        <div className="form-grid">
          <label>{t("portal.templates.form.name")}<input name="name" required pattern="[a-z0-9_]+" placeholder="saludo_inicial" /><span className="field-help">{t("portal.templates.form.nameHelp")}</span></label>
          <label>{t("portal.templates.form.language")}<select name="language" defaultValue="es"><option value="es">Español</option><option value="es_CO">Español (Colombia)</option><option value="es_MX">Español (México)</option><option value="en">English</option><option value="en_US">English (US)</option><option value="pt_BR">Português (BR)</option></select></label>
        </div>
        <label>{t("portal.templates.form.category")}<select name="category" defaultValue="UTILITY"><option value="UTILITY">{t("portal.templates.form.categoryUtility")}</option><option value="MARKETING">{t("portal.templates.form.categoryMarketing")}</option></select></label>
        <label>{t("portal.templates.form.body")}<textarea name="body" rows={4} required value={body} onChange={(e) => setBody(e.target.value)} placeholder={t("portal.templates.form.bodyPlaceholder")} /><span className="field-help">{t("portal.templates.form.bodyHelp")}</span></label>
        {count > 0 && <div className="form-grid">{Array.from({ length: count }, (_, i) => <label key={i}>{t("portal.templates.form.example", { n: String(i + 1) })}<input name={`example${i + 1}`} required /></label>)}</div>}
        <label>{t("portal.templates.form.footer")}<input name="footer" maxLength={60} placeholder={t("portal.templates.form.footerPlaceholder")} /></label>
        {error && <Alert>{error}</Alert>}
        <div className="modal-actions"><button type="button" className="button" onClick={() => setCreating(false)}>{t("portal.contacts.form.cancel")}</button><button className="button primary" disabled={busy}>{busy ? <LoaderCircle className="spin" size={16} /> : t("portal.templates.form.submit")}</button></div>
      </form>
    </Modal>
  </>;
}

/** Pick an approved template and fill its values. Used to start a conversation and to reach out after the window closed. */
export function TemplatePicker({ slug, open, title, onClose, onSend }: { slug: string; open: boolean; title: string; onClose: () => void; onSend: (payload: { name: string; language: string; variables: string[] }) => Promise<void> }) {
  const t = useT();
  const [items, setItems] = useState<Template[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [chosen, setChosen] = useState("");
  const [values, setValues] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const approved = useMemo(() => items.filter((i) => i.status === "APPROVED"), [items]);
  const template = approved.find((i) => `${i.name}|${i.language}` === chosen) || null;

  useEffect(() => {
    if (!open) return;
    setLoading(true); setError(""); setChosen(""); setValues([]);
    api<Template[]>(`/portal/${slug}/templates`).then(setItems).catch((err) => setError(messageFrom(err))).finally(() => setLoading(false));
  }, [open, slug]);
  useEffect(() => { setValues(template ? Array.from({ length: template.variables }, () => "") : []); }, [template]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!template) return;
    setBusy(true); setError("");
    try { await onSend({ name: template.name, language: template.language, variables: values }); onClose(); }
    catch (err) { setError(messageFrom(err)); } finally { setBusy(false); }
  }

  return <Modal open={open} title={title} description={t("portal.templates.pickerDescription")} onClose={onClose}>
    <form className="modal-form" onSubmit={submit}>
      {loading ? <div className="no-conversations"><LoaderCircle className="spin" size={16} /></div> : <>
        <label>{t("portal.templates.pickerLabel")}<select value={chosen} onChange={(e) => setChosen(e.target.value)} required><option value="">{t("portal.templates.pickerPlaceholder")}</option>{approved.map((i) => <option key={`${i.name}|${i.language}`} value={`${i.name}|${i.language}`}>{i.name} · {i.language}</option>)}</select></label>
        {!approved.length && !loading && <Alert type="info">{t("portal.templates.noneApproved")}</Alert>}
        {template && <>
          {template.variables > 0 && <div className="form-grid">{values.map((value, i) => <label key={i}>{t("portal.templates.form.value", { n: String(i + 1) })}<input value={value} required onChange={(e) => setValues(values.map((v, j) => (j === i ? e.target.value : v)))} /></label>)}</div>}
          <div className="template-preview"><span>{t("portal.templates.preview")}</span><p>{renderTemplate(template.body, values)}</p>{template.footer && <small>{template.footer}</small>}</div>
        </>}
      </>}
      {error && <Alert>{error}</Alert>}
      <div className="modal-actions"><button type="button" className="button" onClick={onClose}>{t("portal.contacts.form.cancel")}</button><button className="button primary" disabled={busy || !template || values.some((v) => !v.trim())}>{busy ? <LoaderCircle className="spin" size={16} /> : t("portal.templates.send")}</button></div>
    </form>
  </Modal>;
}
