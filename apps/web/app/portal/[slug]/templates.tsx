"use client";

import { ChangeEvent, DragEvent, FormEvent, ReactNode, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Bold, CheckCircle2, CircleHelp, Clock, Code, Copy, ExternalLink, FileText, Image as ImageIcon, Italic, LoaderCircle, MapPin, Phone, Plus, RefreshCw, Reply, Search, Strikethrough, Trash2, Type, Upload, Video, X, XCircle } from "lucide-react";
import { Alert, EmptyState, Modal } from "@/components/ui";
import { Combobox } from "@/components/combobox";
import { TEMPLATE_VARIABLE, WhatsAppPreview, templateParameters, type PreviewHeader } from "@/components/whatsapp-preview";
import { CONTACT_EXAMPLES, CONTACT_VARIABLES, isContactVariable, type ContactValues } from "@/lib/contact-variables";
import { api, ApiError, messageFrom } from "@/lib/api";
import { useT, type TranslateFn } from "@/lib/i18n";
import { TEMPLATE_LANGUAGES, TEMPLATE_LANGUAGE_CODES, templateLanguageLabel } from "@/lib/template-languages";
import type { Template, TemplateSend } from "@/types";

// The limits Meta enforces, mirrored from the API so the editor can warn
// before submitting.
const LIMITS = { header: 60, body: 1024, footer: 60, button: 25, url: 2000, code: 15, buttons: 10, urls: 2 };

type HeaderFormat = "NONE" | "TEXT" | "IMAGE" | "VIDEO" | "DOCUMENT" | "LOCATION";
type ButtonType = "QUICK_REPLY" | "URL" | "PHONE_NUMBER" | "COPY_CODE";
type DraftButton = { type: ButtonType; text: string; url: string; phone_number: string; example: string };
type Sample = { name: string; url: string; handle: string; uploading: boolean };
type Draft = {
  name: string; language: string; category: "UTILITY" | "MARKETING";
  headerFormat: HeaderFormat; headerText: string; sample: Sample | null;
  body: string; footer: string; buttons: DraftButton[]; examples: Record<string, string>;
};
const EMPTY: Draft = { name: "", language: "es", category: "UTILITY", headerFormat: "NONE", headerText: "", sample: null, body: "", footer: "", buttons: [], examples: {} };
const SAMPLE_ACCEPT: Record<string, string> = { IMAGE: "image/jpeg,image/png", VIDEO: "video/mp4", DOCUMENT: "application/pdf" };

const BUTTON_ICONS: Record<ButtonType, ReactNode> = { QUICK_REPLY: <Reply size={14} />, URL: <ExternalLink size={14} />, PHONE_NUMBER: <Phone size={14} />, COPY_CODE: <Copy size={14} /> };
const HEADER_ICONS: Record<HeaderFormat, ReactNode> = { NONE: null, TEXT: <Type size={14} />, IMAGE: <ImageIcon size={14} />, VIDEO: <Video size={14} />, DOCUMENT: <FileText size={14} />, LOCATION: <MapPin size={14} /> };

function buttonLabel(t: TranslateFn, type: string): string {
  if (type === "URL") return t("portal.templates.form.buttonUrl");
  if (type === "PHONE_NUMBER") return t("portal.templates.form.buttonPhone");
  if (type === "COPY_CODE") return t("portal.templates.form.buttonCopyCode");
  return t("portal.templates.form.buttonQuickReply");
}

function headerLabel(t: TranslateFn, format: string): string {
  if (format === "TEXT") return t("portal.templates.form.headerText");
  if (format === "IMAGE") return t("portal.templates.form.headerImage");
  if (format === "VIDEO") return t("portal.templates.form.headerVideo");
  if (format === "DOCUMENT") return t("portal.templates.form.headerDocument");
  if (format === "LOCATION") return t("portal.templates.form.headerLocation");
  return t("portal.templates.form.headerNone");
}

/** A "?" that opens the guidance for a field: the rule, and a small example. */
function Hint({ text }: { text: string }) {
  return <span className="ai-hint" tabIndex={0} role="note" aria-label={text}><CircleHelp size={14} /><span className="ai-hint-tip wide">{text}</span></span>;
}

function Chars({ n, max }: { n: number; max: number }) {
  const t = useT();
  return <span className={n > max ? "chars over" : "chars"}>{t("portal.templates.form.chars", { n, max })}</span>;
}

// The same checks the API makes, so the editor can point at the field before
// the round trip. Any stray "{{" or "}}" is a variable written wrong.
function braces(text: string): number { return (text.match(/\{\{.*?\}\}|\{\{|\}\}/g) || []).length; }
function variables(text: string): number { return (text.match(TEMPLATE_VARIABLE) || []).length; }

function checkVariables(text: string, out: string[], t: TranslateFn): string[] {
  const names = templateParameters(text);
  if (braces(text) !== variables(text)) out.push(t("portal.templates.rules.variableFormat"));
  const numbered = names.filter((n) => /^[0-9]+$/.test(n));
  if (numbered.length && numbered.length !== names.length) out.push(t("portal.templates.rules.mixed"));
  else if (numbered.length && numbered.map(Number).sort((a, b) => a - b).some((n, i) => n !== i + 1)) out.push(t("portal.templates.rules.gaps"));
  return names;
}

function issuesOf(d: Draft, t: TranslateFn): string[] {
  const out: string[] = [];
  const body = d.body.trim();
  if (!body) out.push(t("portal.templates.rules.bodyEmpty"));
  if (body.length > LIMITS.body) out.push(t("portal.templates.rules.tooLong", { part: t("portal.templates.form.body"), max: LIMITS.body }));
  const bodyNames = checkVariables(body, out, t);
  if (bodyNames.length && (/^\{\{([a-z_]+|[0-9]+)\}\}/.test(body) || /\}\}$/.test(body))) out.push(t("portal.templates.rules.startEnd"));
  let headerNames: string[] = [];
  if (d.headerFormat === "TEXT") {
    const text = d.headerText.trim();
    if (!text) out.push(t("portal.templates.rules.headerEmpty"));
    if (text.length > LIMITS.header) out.push(t("portal.templates.rules.tooLong", { part: t("portal.templates.form.header"), max: LIMITS.header }));
    headerNames = checkVariables(text, out, t);
    if (headerNames.length > 1) out.push(t("portal.templates.rules.headerOneVariable"));
    const numbered = (n: string) => /^[0-9]+$/.test(n);
    if (headerNames.length && bodyNames.length && numbered(headerNames[0]) !== numbered(bodyNames[0])) out.push(t("portal.templates.rules.mixed"));
  } else if (d.headerFormat === "IMAGE" || d.headerFormat === "VIDEO" || d.headerFormat === "DOCUMENT") {
    if (!d.sample?.handle) out.push(t("portal.templates.rules.sampleMissing"));
  }
  const footer = d.footer.trim();
  if (footer.length > LIMITS.footer) out.push(t("portal.templates.rules.tooLong", { part: t("portal.templates.form.footer"), max: LIMITS.footer }));
  if (variables(footer)) out.push(t("portal.templates.rules.footerVariables"));
  // Contact variables bring their own review sample; only custom ones are asked for.
  if ([...headerNames, ...bodyNames].some((n) => !isContactVariable(n) && !(d.examples[n] || "").trim())) out.push(t("portal.templates.rules.examplesMissing"));

  const counts = { QUICK_REPLY: 0, URL: 0, PHONE_NUMBER: 0, COPY_CODE: 0 };
  const seen = new Set<string>();
  const once = (key: string) => { if (!seen.has(key)) { seen.add(key); out.push(key); } };
  d.buttons.forEach((b) => {
    counts[b.type] += 1;
    if (b.type !== "COPY_CODE" && !b.text.trim()) once(t("portal.templates.rules.buttonLabel"));
    if (b.type === "URL") {
      const url = b.url.trim();
      if (!/^https?:\/\//i.test(url)) once(t("portal.templates.rules.buttonUrl"));
      const found = url.match(TEMPLATE_VARIABLE) || [];
      if (found.length > 1 || (found.length === 1 && !url.endsWith("{{1}}"))) once(t("portal.templates.rules.buttonUrlVariable"));
      else if (found.length === 1 && !b.example.trim()) once(t("portal.templates.rules.buttonUrlExample"));
    }
    if (b.type === "PHONE_NUMBER" && !/^\+?[0-9]{5,19}$/.test(b.phone_number.replace(/[\s().-]/g, ""))) once(t("portal.templates.rules.buttonPhone"));
    if (b.type === "COPY_CODE" && (!b.example.trim() || b.example.trim().length > LIMITS.code)) once(t("portal.templates.rules.buttonCode"));
  });
  if (counts.URL > LIMITS.urls) out.push(t("portal.templates.rules.urlCount"));
  if (counts.PHONE_NUMBER > 1) out.push(t("portal.templates.rules.phoneCount"));
  if (counts.COPY_CODE > 1) out.push(t("portal.templates.rules.codeCount"));
  const quick = d.buttons.map((b, i) => (b.type === "QUICK_REPLY" ? i : -1)).filter((i) => i >= 0);
  if (quick.length && (quick[quick.length - 1] - quick[0] + 1 !== quick.length || (quick[0] !== 0 && quick[quick.length - 1] !== d.buttons.length - 1))) out.push(t("portal.templates.rules.quickGroup"));
  return out;
}

function previewHeader(d: Draft): PreviewHeader {
  if (d.headerFormat === "TEXT") return { format: "TEXT", text: d.headerText };
  if (d.headerFormat === "IMAGE" || d.headerFormat === "VIDEO") return { format: d.headerFormat, url: d.sample?.url };
  if (d.headerFormat === "DOCUMENT") return { format: "DOCUMENT", name: d.sample?.name };
  if (d.headerFormat === "LOCATION") return { format: "LOCATION" };
  return { format: "NONE" };
}

function templateHeader(template: Template, values: { url?: string; name?: string; address?: string } = {}): PreviewHeader {
  const header = template.header;
  if (!header) return { format: "NONE" };
  if (header.format === "TEXT") return { format: "TEXT", text: header.text };
  if (header.format === "LOCATION") return { format: "LOCATION", name: values.name, address: values.address };
  if (header.format === "IMAGE" || header.format === "VIDEO") return { format: header.format, url: values.url };
  if (header.format === "DOCUMENT") return { format: "DOCUMENT", name: values.name };
  return { format: "NONE" };
}

/** The WhatsApp templates of the client's business account. `base` is the API
 * prefix (`/portal/{slug}` or `/clients/{id}`). `supported` says whether the
 * client has the API line; left out, the list finds out from the API itself.
 * Without `canManage` the list is read-only. */
export function TemplatesView({ base, supported, canManage = true }: { base: string; supported?: boolean; canManage?: boolean }) {
  const t = useT();
  const [items, setItems] = useState<Template[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [creating, setCreating] = useState(false);
  const [viewing, setViewing] = useState<Template | null>(null);
  const [busy, setBusy] = useState(false);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [removing, setRemoving] = useState<Template | null>(null);
  const [unsupported, setUnsupported] = useState(supported === false);
  useEffect(() => { setUnsupported(supported === false); }, [supported]);
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
    try { setItems(await api<Template[]>(`${base}/templates`)); }
    catch (err) {
      // No API line on this client: the same answer the portal gets told up front.
      if (supported === undefined && err instanceof ApiError && err.status === 409) setUnsupported(true);
      else setError(messageFrom(err));
    }
    finally { setLoading(false); }
  }, [base, supported]);
  useEffect(() => { if (supported === false) setLoading(false); else load(); }, [load, supported]);

  async function remove(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!removing) return;
    setBusy(true); setError("");
    try {
      const query = removing.id ? `?hsm_id=${encodeURIComponent(removing.id)}` : "";
      await api(`${base}/templates/${encodeURIComponent(removing.name)}${query}`, { method: "DELETE" });
      setRemoving(null);
      await load();
    } catch (err) { setError(messageFrom(err)); } finally { setBusy(false); }
  }

  const statusBadge = (status: string) => {
    if (status === "APPROVED") return <span className="mini-badge resolved"><CheckCircle2 size={11} /> {t("portal.templates.status.approved")}</span>;
    if (status === "REJECTED") return <span className="mini-badge rejected"><XCircle size={11} /> {t("portal.templates.status.rejected")}</span>;
    return <span className="mini-badge pending"><Clock size={11} /> {t("portal.templates.status.pending")}</span>;
  };

  if (unsupported) return <EmptyState icon={<Clock />} title={t("portal.templates.unsupportedTitle")} description={t("portal.templates.unsupportedDescription")} />;

  return <>
    <div className="portal-templates">
      <div className="portal-templates-toolbar">
        <p>{t("portal.templates.intro")}</p>
        <div className="portal-templates-actions">
          <button className="button secondary small" onClick={() => load()} disabled={loading} title={t("portal.templates.refresh")}><RefreshCw size={15} className={loading ? "spin" : undefined} /> {t("portal.templates.refresh")}</button>
          {canManage && <button className="button primary small" onClick={() => setCreating(true)}><Plus size={15} /> {t("portal.templates.new")}</button>}
        </div>
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
                  <button type="button" className="link" onClick={() => setViewing(item)} title={t("portal.templates.view")}>{item.name}</button>
                  <small>{item.body}</small>
                  {(item.header || item.buttons.length > 0) && <div className="meta">
                    {item.header && <span className="mini-badge team">{HEADER_ICONS[item.header.format as HeaderFormat]} {headerLabel(t, item.header.format)}</span>}
                    {item.buttons.map((b, i) => <span key={i} className="mini-badge team">{BUTTON_ICONS[b.type as ButtonType]} {b.type === "COPY_CODE" ? buttonLabel(t, b.type) : b.text}</span>)}
                  </div>}
                  {item.status === "REJECTED" && item.rejected_reason && <small className="danger">{item.rejected_reason}</small>}
                </td>
                <td title={templateLanguageLabel(item.language)}>{item.language}</td>
                <td>{item.category.toLowerCase()}{item.previous_category && <small className="template-moved">{t("portal.templates.recategorized", { from: item.previous_category.toLowerCase() })}</small>}</td>
                <td>{statusBadge(item.status)}</td>
                <td className="portal-template-actions">{canManage && <button className="icon-button danger" onClick={() => setRemoving(item)} title={t("portal.templates.delete")} aria-label={t("portal.templates.delete")}><Trash2 size={15} /></button>}</td>
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
    <Modal open={Boolean(viewing)} title={viewing?.name ?? ""} onClose={() => setViewing(null)} wide>
      {viewing && <div className="modal-form template-detail">
        <dl>
          <dt>{t("portal.templates.table.language")}</dt><dd>{templateLanguageLabel(viewing.language)}</dd>
          <dt>{t("portal.templates.table.category")}</dt><dd>{viewing.category.toLowerCase()}</dd>
          <dt>{t("portal.templates.table.status")}</dt><dd>{statusBadge(viewing.status)}{viewing.rejected_reason && <small className="danger"> {viewing.rejected_reason}</small>}</dd>
          {viewing.parameters.length > 0 && <><dt>{t("portal.templates.form.examples")}</dt><dd>{viewing.parameters.map((p) => `{{${p}}}`).join(", ")}</dd></>}
        </dl>
        <WhatsAppPreview header={templateHeader(viewing)} body={viewing.body} footer={viewing.footer} buttons={viewing.buttons} />
      </div>}
    </Modal>
    {creating && <TemplateBuilder base={base} onClose={() => setCreating(false)} onCreated={async () => { setCreating(false); await load(); }} />}
  </>;
}

/** The editor: every part of a template, checked as it is written, next to
 * the message as WhatsApp will show it. */
function TemplateBuilder({ base, onClose, onCreated }: { base: string; onClose: () => void; onCreated: () => Promise<void> }) {
  const t = useT();
  const [d, setD] = useState<Draft>(EMPTY);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [newVar, setNewVar] = useState<string | null>(null);
  const [over, setOver] = useState(false);
  const bodyRef = useRef<HTMLTextAreaElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const patch = (changes: Partial<Draft>) => setD((prev) => ({ ...prev, ...changes }));

  const bodyNames = useMemo(() => templateParameters(d.body), [d.body]);
  const headerNames = useMemo(() => (d.headerFormat === "TEXT" ? templateParameters(d.headerText) : []), [d.headerFormat, d.headerText]);
  const names = useMemo(() => Array.from(new Set([...headerNames, ...bodyNames])), [headerNames, bodyNames]);
  // Contact variables fill themselves; only the custom ones need a sample.
  const customNames = useMemo(() => names.filter((n) => !isContactVariable(n)), [names]);
  const issues = useMemo(() => issuesOf(d, t), [d, t]);
  const languageLabels = useMemo(() => Object.fromEntries(TEMPLATE_LANGUAGE_CODES.map((code) => [code, `${TEMPLATE_LANGUAGES[code]} · ${code}`])), []);

  // Sample previews are object URLs; let them go with the file.
  useEffect(() => () => { if (d.sample?.url) URL.revokeObjectURL(d.sample.url); }, [d.sample?.url]);

  function setHeader(format: HeaderFormat) {
    if (format === d.headerFormat) return;
    patch({ headerFormat: format, sample: null });
  }

  async function pickSample(file: File | null) {
    if (!file) return;
    const url = file.type.startsWith("image/") || file.type.startsWith("video/") ? URL.createObjectURL(file) : "";
    patch({ sample: { name: file.name, url, handle: "", uploading: true } });
    setError("");
    try {
      const form = new FormData();
      form.append("file", file);
      const { handle } = await api<{ handle: string }>(`${base}/templates/samples`, { method: "POST", body: form });
      setD((prev) => (prev.sample?.name === file.name ? { ...prev, sample: { ...prev.sample, handle, uploading: false } } : prev));
    } catch (err) {
      setError(messageFrom(err));
      patch({ sample: null });
    }
  }

  function onDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault(); setOver(false);
    pickSample(event.dataTransfer.files?.[0] ?? null);
  }

  // Wrap the selection with WhatsApp's marks, or drop a pair for the caret.
  function wrap(mark: string) {
    const el = bodyRef.current;
    if (!el) return;
    const [start, end] = [el.selectionStart, el.selectionEnd];
    const inner = d.body.slice(start, end);
    const next = `${d.body.slice(0, start)}${mark}${inner}${mark}${d.body.slice(end)}`;
    patch({ body: next });
    requestAnimationFrame(() => { el.focus(); el.setSelectionRange(start + mark.length, end + mark.length); });
  }

  // Drop a {{name}} at the caret, padding a space when it would touch a word.
  // A contact variable brings its own example so it is ready for review.
  function insertBody(name: string, example?: string) {
    const el = bodyRef.current;
    const at = el ? el.selectionStart : d.body.length;
    const before = d.body.slice(0, at);
    const pad = before && !/\s$/.test(before) ? " " : "";
    const token = `${pad}{{${name}}}`;
    setD((prev) => ({
      ...prev,
      body: `${prev.body.slice(0, at)}${token}${prev.body.slice(at)}`,
      examples: example ? { ...prev.examples, [name]: prev.examples[name] || example } : prev.examples,
    }));
    requestAnimationFrame(() => { if (el) { el.focus(); const caret = at + token.length; el.setSelectionRange(caret, caret); } });
  }

  function insertVariable() {
    const name = (newVar || "").trim();
    if (!name) return;
    insertBody(name);
    setNewVar(null);
  }

  function addButton(type: ButtonType) {
    patch({ buttons: [...d.buttons, { type, text: "", url: "https://", phone_number: "", example: "" }] });
  }
  function setButton(index: number, changes: Partial<DraftButton>) {
    patch({ buttons: d.buttons.map((b, i) => (i === index ? { ...b, ...changes } : b)) });
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (issues.length || d.sample?.uploading) return;
    setBusy(true); setError("");
    try {
      await api<Template>(`${base}/templates`, { method: "POST", body: JSON.stringify({
        name: d.name.trim().toLowerCase(),
        language: d.language,
        category: d.category,
        header: d.headerFormat === "NONE" ? null : { format: d.headerFormat, text: d.headerText.trim(), handle: d.sample?.handle || "" },
        body: d.body.trim(),
        footer: d.footer.trim(),
        buttons: d.buttons.map((b) => ({ type: b.type, text: b.text.trim(), url: b.url.trim(), phone_number: b.phone_number.trim(), example: b.example.trim() })),
        examples: Object.fromEntries(names.map((n) => [n, (d.examples[n] || (isContactVariable(n) ? CONTACT_EXAMPLES[n] : "")).trim()])),
      }) });
      await onCreated();
    } catch (err) { setError(messageFrom(err)); } finally { setBusy(false); }
  }

  const media = d.headerFormat === "IMAGE" || d.headerFormat === "VIDEO" || d.headerFormat === "DOCUMENT";
  const previewButtons = d.buttons.map((b) => ({ type: b.type, text: b.text }));
  // Contact variables preview with their stand-in even when typed by hand.
  const previewValues = { ...Object.fromEntries(names.filter(isContactVariable).map((n) => [n, CONTACT_EXAMPLES[n]])), ...d.examples };

  return <Modal open title={t("portal.templates.newTitle")} description={t("portal.templates.newDescription")} onClose={onClose} wide>
    <form className="modal-form template-builder" onSubmit={submit}>
      <div className="template-builder-form">
        <div className="form-grid">
          <label>
            <span className="label-row">{t("portal.templates.form.name")}<Hint text={t("portal.templates.tips.name")} /></span>
            <input value={d.name} onChange={(e) => patch({ name: e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, "_") })} required pattern="[a-z0-9_]+" placeholder={t("portal.templates.form.namePlaceholder")} />
            <span className="field-help">{t("portal.templates.form.nameHelp")}</span>
          </label>
          <label>
            <span className="label-row">{t("portal.templates.form.language")}<Hint text={t("portal.templates.tips.language")} /></span>
            <Combobox value={d.language} onChange={(language) => patch({ language })} options={TEMPLATE_LANGUAGE_CODES} labels={languageLabels} placeholder={t("portal.templates.form.languagePlaceholder")} />
          </label>
        </div>
        <label>
          <span className="label-row">{t("portal.templates.form.category")}<Hint text={t("portal.templates.tips.category")} /></span>
          <select value={d.category} onChange={(e) => patch({ category: e.target.value as Draft["category"] })}>
            <option value="UTILITY">{t("portal.templates.form.categoryUtility")}</option>
            <option value="MARKETING">{t("portal.templates.form.categoryMarketing")}</option>
          </select>
        </label>

        <div className="stack-field">
          <span className="label-row"><strong>{t("portal.templates.form.header")}</strong><Hint text={t("portal.templates.tips.header")} /></span>
          <div className="template-header-kinds">
            {(["NONE", "TEXT", "IMAGE", "VIDEO", "DOCUMENT", "LOCATION"] as HeaderFormat[]).map((format) => (
              <button key={format} type="button" className={d.headerFormat === format ? "active" : ""} onClick={() => setHeader(format)}>{HEADER_ICONS[format]}{headerLabel(t, format)}</button>
            ))}
          </div>
          {d.headerFormat === "TEXT" && <label>
            <span className="label-row"><Chars n={d.headerText.length} max={LIMITS.header} /></span>
            <input value={d.headerText} onChange={(e) => patch({ headerText: e.target.value })} maxLength={LIMITS.header + 20} placeholder={t("portal.templates.form.headerTextPlaceholder")} />
          </label>}
          {media && <>
            <input ref={fileRef} type="file" accept={SAMPLE_ACCEPT[d.headerFormat]} hidden onChange={(e: ChangeEvent<HTMLInputElement>) => { pickSample(e.target.files?.[0] ?? null); e.target.value = ""; }} />
            <div className={`template-dropzone${over ? " over" : ""}${d.sample ? " ready" : ""}`} role="button" tabIndex={0}
              onClick={() => fileRef.current?.click()} onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); fileRef.current?.click(); } }}
              onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)} onDrop={onDrop}>
              {d.sample ? <>
                <span className="file">
                  {d.sample.url && d.headerFormat === "IMAGE" ? <img className="thumb" src={d.sample.url} alt="" /> : HEADER_ICONS[d.headerFormat]}
                  <span>{d.sample.name}</span>
                  {d.sample.uploading && <LoaderCircle className="spin" size={14} />}
                </span>
                <span className="field-help">{d.sample.uploading ? t("portal.templates.form.sampleUploading") : t("portal.templates.form.sampleReplace")}</span>
              </> : <><Upload size={16} />{t("portal.templates.form.sampleDrop")}</>}
            </div>
            <span className="field-help">{t("portal.templates.form.sampleFormats")}</span>
          </>}
          {d.headerFormat === "LOCATION" && <span className="field-help">{t("portal.templates.form.locationHelp")}</span>}
        </div>

        <label>
          <span className="label-row">{t("portal.templates.form.body")}<Hint text={t("portal.templates.tips.body")} /><Chars n={d.body.length} max={LIMITS.body} /></span>
          <textarea ref={bodyRef} rows={6} required value={d.body} onChange={(e) => patch({ body: e.target.value })} placeholder={t("portal.templates.form.bodyPlaceholder")} />
          <div className="template-toolbar">
            <button type="button" className="icon-button" title={t("portal.templates.form.bold")} aria-label={t("portal.templates.form.bold")} onClick={() => wrap("*")}><Bold size={14} /></button>
            <button type="button" className="icon-button" title={t("portal.templates.form.italic")} aria-label={t("portal.templates.form.italic")} onClick={() => wrap("_")}><Italic size={14} /></button>
            <button type="button" className="icon-button" title={t("portal.templates.form.strike")} aria-label={t("portal.templates.form.strike")} onClick={() => wrap("~")}><Strikethrough size={14} /></button>
            <button type="button" className="icon-button" title={t("portal.templates.form.mono")} aria-label={t("portal.templates.form.mono")} onClick={() => wrap("```")}><Code size={14} /></button>
            <span className="spacer" />
            {newVar === null ? <button type="button" className="button small" onClick={() => setNewVar("")}><Plus size={14} /> {t("portal.templates.form.addVariable")}</button>
              : <span className="template-variable-add">
                <input autoFocus value={newVar} placeholder={t("portal.templates.form.variableNamePlaceholder")} onChange={(e) => setNewVar(e.target.value.toLowerCase().replace(/[\s-]+/g, "_").replace(/[^a-z_]/g, ""))} onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); insertVariable(); } if (e.key === "Escape") setNewVar(null); }} />
                <button type="button" className="button primary small" onClick={insertVariable} disabled={!newVar}>{t("portal.templates.form.insert")}</button>
                <button type="button" className="icon-button" onClick={() => setNewVar(null)} aria-label={t("portal.contacts.form.cancel")}><X size={14} /></button>
              </span>}
          </div>
          <div className="template-contact-vars">
            <span>{t("portal.templates.form.contactVars")}</span>
            {CONTACT_VARIABLES.map((name) => <button type="button" key={name} onClick={() => insertBody(name, CONTACT_EXAMPLES[name])}>{`{{${name}}}`}</button>)}
          </div>
          <span className="field-help">{t("portal.templates.form.bodyHelp")}</span>
        </label>

        {customNames.length > 0 && <div className="stack-field">
          <span className="label-row"><strong>{t("portal.templates.form.examples")}</strong><Hint text={t("portal.templates.tips.variables")} /></span>
          <table className="template-examples"><tbody>{customNames.map((n) => <tr key={n}>
            <th><code>{`{{${n}}}`}</code></th>
            <td><input value={d.examples[n] || ""} required placeholder={t("portal.templates.form.examplePlaceholder")} onChange={(e) => patch({ examples: { ...d.examples, [n]: e.target.value } })} /></td>
          </tr>)}</tbody></table>
          <span className="field-help">{t("portal.templates.form.examplesHelp")}</span>
        </div>}

        <label>
          <span className="label-row">{t("portal.templates.form.footer")}<Hint text={t("portal.templates.tips.footer")} /><Chars n={d.footer.length} max={LIMITS.footer} /></span>
          <input value={d.footer} onChange={(e) => patch({ footer: e.target.value })} maxLength={LIMITS.footer + 20} placeholder={t("portal.templates.form.footerPlaceholder")} />
        </label>

        <div className="stack-field template-buttons">
          <span className="label-row"><strong>{t("portal.templates.form.buttons")}</strong><Hint text={t("portal.templates.tips.buttons")} /></span>
          {d.buttons.map((b, i) => <div key={i} className="template-button-row">
            <span className="kind">{BUTTON_ICONS[b.type]} {buttonLabel(t, b.type)}</span>
            <div className="fields">
              {b.type !== "COPY_CODE" && <input value={b.text} maxLength={LIMITS.button} placeholder={t("portal.templates.form.buttonLabel")} aria-label={t("portal.templates.form.buttonLabel")} onChange={(e) => setButton(i, { text: e.target.value })} />}
              {b.type === "URL" && <>
                <input value={b.url} maxLength={LIMITS.url} placeholder="https://" aria-label={t("portal.templates.form.buttonUrlField")} onChange={(e) => setButton(i, { url: e.target.value })} />
                {b.url.includes("{{1}}") ? <input value={b.example} placeholder={t("portal.templates.form.buttonUrlExample")} aria-label={t("portal.templates.form.buttonUrlExample")} onChange={(e) => setButton(i, { example: e.target.value })} /> : <span className="field-help">{t("portal.templates.form.buttonUrlHelp")}</span>}
              </>}
              {b.type === "PHONE_NUMBER" && <input value={b.phone_number} maxLength={24} placeholder="+57 300 123 4567" aria-label={t("portal.templates.form.buttonPhoneField")} onChange={(e) => setButton(i, { phone_number: e.target.value })} />}
              {b.type === "COPY_CODE" && <input value={b.example} maxLength={LIMITS.code} placeholder={t("portal.templates.form.buttonCodeExample")} aria-label={t("portal.templates.form.buttonCodeExample")} onChange={(e) => setButton(i, { example: e.target.value })} />}
            </div>
            <button type="button" className="icon-button danger" onClick={() => patch({ buttons: d.buttons.filter((_, j) => j !== i) })} title={t("portal.templates.form.removeButton")} aria-label={t("portal.templates.form.removeButton")}><Trash2 size={14} /></button>
          </div>)}
          {d.buttons.length < LIMITS.buttons && <select value="" onChange={(e) => { if (e.target.value) addButton(e.target.value as ButtonType); }} aria-label={t("portal.templates.form.addButton")}>
            <option value="">{t("portal.templates.form.addButton")}</option>
            <option value="QUICK_REPLY">{t("portal.templates.form.buttonQuickReply")}</option>
            <option value="URL">{t("portal.templates.form.buttonUrl")}</option>
            <option value="PHONE_NUMBER">{t("portal.templates.form.buttonPhone")}</option>
            <option value="COPY_CODE">{t("portal.templates.form.buttonCopyCode")}</option>
          </select>}
        </div>
      </div>

      <aside className="template-builder-side">
        <span>{t("portal.templates.preview.title")}</span>
        <WhatsAppPreview header={previewHeader(d)} body={d.body} footer={d.footer} buttons={previewButtons} values={previewValues} empty={t("portal.templates.preview.empty")} />
        {names.length > 0 && <small>{t("portal.templates.preview.examplesNote")}</small>}
      </aside>

      {issues.length > 0 && (d.body || d.headerFormat !== "NONE" || d.buttons.length > 0) && <ul className="template-issues" aria-label={t("portal.templates.form.fix")}>{issues.map((issue) => <li key={issue}>{issue}</li>)}</ul>}
      {error && <Alert>{error}</Alert>}
      <div className="modal-actions"><button type="button" className="button" onClick={onClose}>{t("portal.contacts.form.cancel")}</button><button className="button primary" disabled={busy || issues.length > 0 || Boolean(d.sample?.uploading)}>{busy ? <LoaderCircle className="spin" size={16} /> : t("portal.templates.form.submit")}</button></div>
    </form>
  </Modal>;
}

/** Pick an approved template and fill its values. Used to start a conversation and to reach out after the window closed. */
export function TemplatePicker({ base, open, title, contactValues, onClose, onSend }: { base: string; open: boolean; title: string; contactValues?: ContactValues; onClose: () => void; onSend: (payload: TemplateSend) => Promise<void> }) {
  const t = useT();
  const [items, setItems] = useState<Template[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [chosen, setChosen] = useState("");
  const [values, setValues] = useState<Record<string, string>>({});
  const [headerValue, setHeaderValue] = useState("");
  const [place, setPlace] = useState({ latitude: "", longitude: "", name: "", address: "" });
  const [buttonValues, setButtonValues] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const approved = useMemo(() => items.filter((i) => i.status === "APPROVED"), [items]);
  const template = approved.find((i) => `${i.name}|${i.language}` === chosen) || null;

  useEffect(() => {
    if (!open) return;
    setLoading(true); setError(""); setChosen("");
    api<Template[]>(`${base}/templates`).then(setItems).catch((err) => setError(messageFrom(err))).finally(() => setLoading(false));
  }, [open, base]);
  // A variable named after a contact property starts filled from the contact,
  // so it never travels empty; the operator can still edit it.
  const prefill = (name: string) => (contactValues && isContactVariable(name) ? contactValues[name] : "");
  useEffect(() => {
    setValues(template ? Object.fromEntries(template.parameters.map((n) => [n, prefill(n)])) : {});
    const headerName = template?.header?.format === "TEXT" ? template.header.parameters[0] : undefined;
    setHeaderValue(headerName ? prefill(headerName) : "");
    setPlace({ latitude: "", longitude: "", name: "", address: "" });
    setButtonValues(template ? template.buttons.map(() => "") : []);
  }, [template]);

  const header = template?.header ?? null;
  const headerParam = header?.format === "TEXT" ? header.parameters[0] : undefined;
  const media = header && (header.format === "IMAGE" || header.format === "VIDEO" || header.format === "DOCUMENT");
  const dynamic = (template?.buttons ?? []).map((b, i) => ({ ...b, index: i })).filter((b) => b.dynamic);
  const missing = !template
    || template.parameters.some((n) => !(values[n] || "").trim())
    || (headerParam !== undefined && !headerValue.trim())
    || (Boolean(media) && !/^https:\/\//i.test(headerValue.trim()))
    || (header?.format === "LOCATION" && (place.latitude.trim() === "" || place.longitude.trim() === "" || Number.isNaN(Number(place.latitude)) || Number.isNaN(Number(place.longitude))))
    || dynamic.some((b) => !(buttonValues[b.index] || "").trim());

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!template || missing) return;
    setBusy(true); setError("");
    try {
      await onSend({
        name: template.name,
        language: template.language,
        variables: template.parameters.map((n) => (values[n] || "").trim()),
        header_value: headerValue.trim(),
        location: header?.format === "LOCATION" ? { latitude: Number(place.latitude), longitude: Number(place.longitude), name: place.name.trim(), address: place.address.trim() } : null,
        button_values: buttonValues.map((v) => v.trim()),
      });
      onClose();
    }
    catch (err) { setError(messageFrom(err)); } finally { setBusy(false); }
  }

  const previewValues = headerParam ? { ...values, [headerParam]: headerValue } : values;
  const mediaKind = header ? headerLabel(t, header.format).toLowerCase() : "";

  return <Modal open={open} title={title} description={t("portal.templates.pickerDescription")} onClose={onClose} wide={Boolean(template)}>
    <form className={template ? "modal-form template-builder" : "modal-form"} onSubmit={submit}>
      <div className="template-builder-form">
        {loading ? <div className="no-conversations"><LoaderCircle className="spin" size={16} /></div> : <>
          <label>{t("portal.templates.pickerLabel")}<select value={chosen} onChange={(e) => setChosen(e.target.value)} required><option value="">{t("portal.templates.pickerPlaceholder")}</option>{approved.map((i) => <option key={`${i.name}|${i.language}`} value={`${i.name}|${i.language}`}>{i.name} · {i.language}</option>)}</select></label>
          {!approved.length && !loading && <Alert type="info">{t("portal.templates.noneApproved")}</Alert>}
          {template && <>
            {headerParam !== undefined && <label>{t("portal.templates.form.value", { n: headerParam })}<input value={headerValue} required onChange={(e) => setHeaderValue(e.target.value)} /></label>}
            {media && <label>{t("portal.templates.sendForm.mediaLink", { kind: mediaKind })}<input type="url" value={headerValue} required placeholder="https://" onChange={(e) => setHeaderValue(e.target.value)} /></label>}
            {header?.format === "LOCATION" && <div className="form-grid">
              <label>{t("portal.templates.sendForm.latitude")}<input value={place.latitude} required inputMode="decimal" placeholder="4.6533" onChange={(e) => setPlace({ ...place, latitude: e.target.value })} /></label>
              <label>{t("portal.templates.sendForm.longitude")}<input value={place.longitude} required inputMode="decimal" placeholder="-74.0836" onChange={(e) => setPlace({ ...place, longitude: e.target.value })} /></label>
              <label>{t("portal.templates.sendForm.placeName")}<input value={place.name} onChange={(e) => setPlace({ ...place, name: e.target.value })} /></label>
              <label>{t("portal.templates.sendForm.address")}<input value={place.address} onChange={(e) => setPlace({ ...place, address: e.target.value })} /></label>
            </div>}
            {template.parameters.length > 0 && <div className="form-grid">{template.parameters.map((n) => <label key={n}>{t("portal.templates.form.value", { n })}<input value={values[n] || ""} required onChange={(e) => setValues({ ...values, [n]: e.target.value })} /></label>)}</div>}
            {dynamic.map((b) => <label key={b.index}>
              {b.type === "COPY_CODE" ? t("portal.templates.sendForm.buttonCode") : t("portal.templates.sendForm.buttonUrl", { text: b.text })}
              <input value={buttonValues[b.index] || ""} required maxLength={b.type === "COPY_CODE" ? LIMITS.code : 200} placeholder={b.example} onChange={(e) => setButtonValues(buttonValues.map((v, j) => (j === b.index ? e.target.value : v)))} />
            </label>)}
          </>}
        </>}
      </div>
      {template && <aside className="template-builder-side template-picker-preview">
        <span>{t("portal.templates.preview.title")}</span>
        <WhatsAppPreview
          header={templateHeader(template, { url: /^https:\/\//i.test(headerValue.trim()) ? headerValue.trim() : undefined, name: header?.format === "LOCATION" ? place.name : headerValue.split("/").pop(), address: place.address })}
          body={template.body} footer={template.footer} buttons={template.buttons} values={previewValues} />
      </aside>}
      {error && <Alert>{error}</Alert>}
      <div className="modal-actions"><button type="button" className="button" onClick={onClose}>{t("portal.contacts.form.cancel")}</button><button className="button primary" disabled={busy || missing}>{busy ? <LoaderCircle className="spin" size={16} /> : t("portal.templates.send")}</button></div>
    </form>
  </Modal>;
}
