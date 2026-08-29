"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { CheckCircle2, Clock, LoaderCircle, Plus, XCircle } from "lucide-react";
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
  const count = variableCount(body);

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
      {error && !creating && <Alert>{error}</Alert>}
      {loading ? <div className="no-conversations"><LoaderCircle className="spin" size={16} /></div>
        : items.length ? <div className="portal-template-list">{items.map((item) => <article key={`${item.name}-${item.language}`}>
          <header><strong>{item.name}</strong><small>{item.language} · {item.category.toLowerCase()}</small>{statusBadge(item.status)}</header>
          <p>{item.body}</p>
          {item.footer && <small className="muted">{item.footer}</small>}
          {item.status === "REJECTED" && item.rejected_reason && <small className="danger">{item.rejected_reason}</small>}
        </article>)}</div>
        : <EmptyState icon={<Clock />} title={t("portal.templates.emptyTitle")} description={t("portal.templates.emptyDescription")} />}
    </div>
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
