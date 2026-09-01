"use client";

import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft, AudioLines, Bot, CheckCircle2, Code, Copy, ExternalLink, FileText, ImageIcon, LoaderCircle, MessageSquareText, Plus, Power, PowerOff, Save, Settings2, Sparkles, Trash2, UploadCloud, Wrench, XCircle } from "lucide-react";
import { api, messageFrom } from "@/lib/api";
import { useT } from "@/lib/i18n";
import { Alert } from "@/components/ui";
import { FormSkeleton } from "@/components/skeleton";
import { useToast } from "@/components/toast";
import { ChatPlayground } from "@/components/chat-playground";
import { AgentToolsTab } from "@/components/agent-tools/agent-tools-tab";
import { EscalationRulesEditor } from "@/components/escalation-rules";
import { Combobox } from "@/components/combobox";
import { PROVIDERS, modelsFor, defaultModelFor, estimateTokens, modelContextWindow, AUDIO_MODELS, IMAGE_MODELS } from "@/lib/providers";
import { TIMEZONES } from "@/lib/timezones";
import type { Agent, AgentTool, Client, KnowledgeDocument, QAPair } from "@/types";

type Tab = "details" | "knowledge" | "tools" | "widget" | "playground";

export default function AgentDetailPage() {
  const t = useT();
  const toast = useToast();
  const { id } = useParams<{ id: string }>();
  const [agent, setAgent] = useState<Agent | null>(null);
  const [clients, setClients] = useState<Client[]>([]);
  const [provider, setProvider] = useState("openai");
  const [model, setModel] = useState("");
  const [timezone, setTimezone] = useState("UTC");
  const [temperature, setTemperature] = useState(0.7);
  const [maxTokens, setMaxTokens] = useState(2048);
  const [memoryLimit, setMemoryLimit] = useState(30);
  const [imageEnabled, setImageEnabled] = useState(false);
  const [imageModel, setImageModel] = useState("gpt-4.1");
  const [audioEnabled, setAudioEnabled] = useState(false);
  const [audioModel, setAudioModel] = useState("whisper-1");
  const [widgetEnabled, setWidgetEnabled] = useState(false);
  const [widgetGreeting, setWidgetGreeting] = useState("");
  const [widgetColor, setWidgetColor] = useState("#075985");
  const [widgetPosition, setWidgetPosition] = useState("right");
  const [documents, setDocuments] = useState<KnowledgeDocument[]>([]);
  const [qaPairs, setQaPairs] = useState<QAPair[]>([]);
  const [tools, setTools] = useState<AgentTool[]>([]);
  const [tab, setTab] = useState<Tab>("details");
  const [busy, setBusy] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const load = async () => {
    const [a, c, d, q, tl] = await Promise.all([api<Agent>(`/agents/${id}`), api<Client[]>("/clients"), api<KnowledgeDocument[]>(`/agents/${id}/documents`), api<QAPair[]>(`/agents/${id}/qa`), api<AgentTool[]>(`/agents/${id}/tools`)]);
    setAgent(a); setClients(c); setDocuments(d); setQaPairs(q); setTools(tl);
    setProvider(a.provider); setModel(a.model); setTimezone(a.timezone || "UTC");
    setTemperature(a.temperature); setMaxTokens(a.max_tokens); setMemoryLimit(a.memory_limit);
    setImageEnabled(a.image_enabled); setImageModel(a.image_model || "gpt-4.1");
    setAudioEnabled(a.audio_enabled); setAudioModel(a.audio_model || "whisper-1");
    setWidgetEnabled(a.widget_enabled); setWidgetGreeting(a.widget_greeting);
    setWidgetColor(a.widget_color || "#075985"); setWidgetPosition(a.widget_position || "right");
  };

  const contextWindow = modelContextWindow(model);
  const promptTokens = useMemo(
    () => (agent ? estimateTokens([agent.description, agent.instructions, agent.personality, agent.brief_summary, agent.brief_products, agent.brief_audience, agent.brief_policies, agent.brief_goal, agent.brief_dos, agent.brief_donts, agent.manual_context].join("\n")) : 0),
    [agent],
  );
  const contextPct = Math.min(100, Math.round((promptTokens / contextWindow) * 100));
  useEffect(() => { load(); }, [id]);
  // Let other areas deep-link straight to a tab, e.g. the Channels page pointing at "?tab=widget".
  useEffect(() => { const q = new URLSearchParams(window.location.search).get("tab"); if (q === "knowledge" || q === "tools" || q === "widget" || q === "playground") setTab(q); }, []);

  async function saveConfig(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true);
    const form = new FormData(event.currentTarget);
    const payload = { client_id: form.get("client_id"), name: form.get("name"), description: form.get("description"), instructions: form.get("instructions"), personality: form.get("personality"), brief_summary: form.get("brief_summary"), brief_products: form.get("brief_products"), brief_audience: form.get("brief_audience"), brief_policies: form.get("brief_policies"), brief_goal: form.get("brief_goal"), brief_dos: form.get("brief_dos"), brief_donts: form.get("brief_donts"), provider, model, timezone, temperature, max_tokens: maxTokens, memory_limit: memoryLimit, image_enabled: imageEnabled, image_model: imageModel, audio_enabled: audioEnabled, audio_model: audioModel };
    try { setAgent(await api<Agent>(`/agents/${id}`, { method: "PATCH", body: JSON.stringify(payload) })); toast.success(t("agents.detail.configSaved")); }
    catch (err) { toast.error(messageFrom(err)); } finally { setBusy(false); }
  }

  async function togglePublish() {
    if (!agent) return;
    setBusy(true);
    try {
      const updated = await api<Agent>(`/agents/${id}`, { method: "PATCH", body: JSON.stringify({ is_active: !agent.is_active }) });
      setAgent(updated);
      toast.success(updated.is_active ? t("agents.detail.publishedNotice") : t("agents.detail.unpublishedNotice"));
    } catch (err) { toast.error(messageFrom(err)); } finally { setBusy(false); }
  }

  async function saveContext(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true);
    const form = new FormData(event.currentTarget);
    try { setAgent(await api<Agent>(`/agents/${id}/context`, { method: "PUT", body: JSON.stringify({ manual_context: form.get("manual_context") }) })); toast.success(t("agents.detail.manualContextSaved")); }
    catch (err) { toast.error(messageFrom(err)); } finally { setBusy(false); }
  }

  async function saveWidget(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true);
    const payload = { widget_enabled: widgetEnabled, widget_greeting: widgetGreeting, widget_color: widgetColor, widget_position: widgetPosition };
    try { setAgent(await api<Agent>(`/agents/${id}`, { method: "PATCH", body: JSON.stringify(payload) })); toast.success(t("agents.detail.widgetSaved")); }
    catch (err) { toast.error(messageFrom(err)); } finally { setBusy(false); }
  }

  const widgetSnippet = agent
    ? `<script src="${typeof window === "undefined" ? "" : window.location.origin}/widget.js" data-agent="${agent.widget_public_id}" data-color="${widgetColor}" data-position="${widgetPosition}" async></script>`
    : "";

  async function upload(file: File | undefined) {
    if (!file) return;
    setBusy(true);
    const data = new FormData(); data.append("file", file);
    try { const doc = await api<KnowledgeDocument>(`/agents/${id}/documents`, { method: "POST", body: data }); setDocuments((items) => [doc, ...items]); toast.success(doc.status === "processed" ? t("agents.detail.pdfProcessed") : t("agents.detail.pdfSavedNotProcessed")); }
    catch (err) { toast.error(messageFrom(err)); } finally { setBusy(false); if (fileRef.current) fileRef.current.value = ""; }
  }

  async function removeDocument(doc: KnowledgeDocument) {
    if (!confirm(t("agents.detail.confirmDelete", { filename: doc.filename }))) return;
    await api(`/agents/${id}/documents/${doc.id}`, { method: "DELETE" });
    setDocuments((items) => items.filter((item) => item.id !== doc.id));
  }

  async function addQA(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true);
    const form = event.currentTarget;
    const data = new FormData(form);
    try {
      const pair = await api<QAPair>(`/agents/${id}/qa`, { method: "POST", body: JSON.stringify({ question: data.get("question"), answer: data.get("answer") }) });
      setQaPairs((items) => [...items, pair]);
      form.reset();
    } catch (err) { toast.error(messageFrom(err)); } finally { setBusy(false); }
  }
  async function removeQA(pair: QAPair) {
    await api(`/agents/${id}/qa/${pair.id}`, { method: "DELETE" });
    setQaPairs((items) => items.filter((item) => item.id !== pair.id));
  }

  if (!agent) return <div className="page"><FormSkeleton sections={2} /></div>;
  return <div className="page agent-detail-page">
    <Link href="/agents" className="back-link"><ArrowLeft size={16} /> {t("agents.detail.back")}</Link>
    <header className="agent-detail-head"><div className="agent-title-wrap"><span className="agent-avatar xl"><Bot size={29} /></span><div><div className="title-line"><h1>{agent.name}</h1><span className={agent.is_active ? "pill purple" : "pill"}>{agent.is_active ? t("agents.detail.published") : t("agents.detail.unpublished")}</span></div><p>{agent.client.name} · {agent.description || t("agents.detail.noDescription")}</p></div></div><div className="header-actions"><button className={agent.is_active ? "button ghost" : "button primary"} onClick={togglePublish} disabled={busy}>{agent.is_active ? <><PowerOff size={16} /> {t("agents.detail.unpublish")}</> : <><Power size={16} /> {t("agents.detail.publish")}</>}</button><Link href={`/playground`} className="button secondary"><MessageSquareText size={17} /> {t("agents.detail.openPlayground")}</Link></div></header>
    <nav className="tabs"><button className={tab === "details" ? "active" : ""} onClick={() => setTab("details")}><Settings2 size={17} /> {t("agents.detail.tabDetails")}</button><button className={tab === "knowledge" ? "active" : ""} onClick={() => setTab("knowledge")}><FileText size={17} /> {t("agents.detail.tabKnowledge")} <span>{documents.length}</span></button><button className={tab === "tools" ? "active" : ""} onClick={() => setTab("tools")}><Wrench size={17} /> {t("tools.tab")} <span>{tools.length}</span></button><button className={tab === "widget" ? "active" : ""} onClick={() => setTab("widget")}><Code size={17} /> {t("agents.detail.tabWidget")}</button><button className={tab === "playground" ? "active" : ""} onClick={() => setTab("playground")}><MessageSquareText size={17} /> {t("agents.detail.tabPlayground")}</button></nav>

    {tab === "details" && <form className="settings-form" onSubmit={saveConfig}>
      <section className="settings-section"><div className="settings-copy"><h3>{t("agents.detail.generalHeading")}</h3><p>{t("agents.detail.generalCopy")}</p></div><div className="settings-fields"><div className="form-grid"><label>{t("agents.detail.clientLabel")}<select name="client_id" defaultValue={agent.client_id}>{clients.map((client) => <option key={client.id} value={client.id}>{client.name}</option>)}</select></label><label>{t("agents.detail.nameLabel")}<input name="name" required defaultValue={agent.name} /></label></div><label>{t("agents.detail.descriptionLabel")}<textarea name="description" rows={3} defaultValue={agent.description} /></label></div></section>
      <section className="settings-section"><div className="settings-copy"><h3>{t("agents.detail.behaviorHeading")}</h3><p>{t("agents.detail.behaviorCopy")}</p></div><div className="settings-fields"><label>{t("agents.detail.instructionsLabel")}<textarea name="instructions" rows={8} defaultValue={agent.instructions} placeholder={t("agents.detail.instructionsPlaceholder")} /></label><label>{t("agents.detail.personalityLabel")}<textarea name="personality" rows={4} defaultValue={agent.personality} placeholder={t("agents.detail.personalityPlaceholder")} /></label></div></section>
      <EscalationRulesEditor agentId={agent.id} clientId={agent.client_id} />
      <section className="settings-section"><div className="settings-copy"><h3>{t("agents.detail.briefHeading")}</h3><p>{t("agents.detail.briefCopy")}</p></div><div className="settings-fields">
        <label>{t("agents.detail.briefSummaryLabel")}<textarea name="brief_summary" rows={2} defaultValue={agent.brief_summary} placeholder={t("agents.detail.briefSummaryPlaceholder")} /></label>
        <div className="form-grid">
          <label>{t("agents.detail.briefProductsLabel")}<textarea name="brief_products" rows={3} defaultValue={agent.brief_products} placeholder={t("agents.detail.briefProductsPlaceholder")} /></label>
          <label>{t("agents.detail.briefAudienceLabel")}<textarea name="brief_audience" rows={3} defaultValue={agent.brief_audience} placeholder={t("agents.detail.briefAudiencePlaceholder")} /></label>
        </div>
        <label>{t("agents.detail.briefPoliciesLabel")}<textarea name="brief_policies" rows={3} defaultValue={agent.brief_policies} placeholder={t("agents.detail.briefPoliciesPlaceholder")} /></label>
        <label>{t("agents.detail.briefGoalLabel")}<textarea name="brief_goal" rows={2} defaultValue={agent.brief_goal} placeholder={t("agents.detail.briefGoalPlaceholder")} /></label>
        <div className="form-grid">
          <label>{t("agents.detail.briefDosLabel")}<textarea name="brief_dos" rows={3} defaultValue={agent.brief_dos} placeholder={t("agents.detail.briefDosPlaceholder")} /></label>
          <label>{t("agents.detail.briefDontsLabel")}<textarea name="brief_donts" rows={3} defaultValue={agent.brief_donts} placeholder={t("agents.detail.briefDontsPlaceholder")} /></label>
        </div>
      </div></section>
      <section className="settings-section"><div className="settings-copy"><h3>{t("agents.detail.aiModelHeading")}</h3><p>{t("agents.detail.aiModelCopy")}</p></div><div className="settings-fields">
        <label>{t("agents.detail.timezoneLabel")}<Combobox value={timezone} onChange={setTimezone} options={TIMEZONES} placeholder={t("agents.detail.timezoneLabel")} /></label>
        <div className="form-grid"><label>{t("agents.detail.providerLabel")}<select value={provider} onChange={(e) => { setProvider(e.target.value); if (!modelsFor(e.target.value).includes(model)) setModel(defaultModelFor(e.target.value)); }}>{PROVIDERS.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}</select></label><label>{t("agents.detail.modelLabel")}<Combobox value={model} onChange={setModel} options={modelsFor(provider)} placeholder={t("agents.detail.modelPlaceholder")} allowCustom /></label></div>
        <div className="context-bar"><div style={{ width: `${contextPct}%` }} /><small><Sparkles size={12} /> {t("agents.detail.contextUsage", { count: promptTokens.toLocaleString("es"), total: contextWindow.toLocaleString("es") })}</small></div>
        <Alert type="info">{t("agents.detail.providerKeysPrefix")}<Link href="/settings">{t("agents.detail.settingsLink")}</Link>.</Alert>
        <details className="advanced-options wizard-advanced"><summary>{t("agents.detail.advancedHeading")}</summary><p className="field-help">{t("agents.detail.advancedCopy")}</p>
        <div className="slider-field"><div className="slider-head"><span>{t("agents.detail.temperatureLabel")}</span><strong>{temperature.toFixed(1)}/2</strong></div><input type="range" min="0" max="2" step="0.1" value={temperature} onChange={(e) => setTemperature(Number(e.target.value))} /><span className="field-help">{t("agents.detail.temperatureHint")}</span></div>
        <div className="slider-field"><div className="slider-head"><span>{t("agents.detail.maxTokensLabel")}</span><strong>{maxTokens}/8192</strong></div><input type="range" min="256" max="8192" step="256" value={maxTokens} onChange={(e) => setMaxTokens(Number(e.target.value))} /><span className="field-help">{t("agents.detail.maxTokensHint")}</span></div>
        <div className="slider-field"><div className="slider-head"><span>{t("agents.detail.memoryLimitLabel")}</span><strong>{memoryLimit}/100</strong></div><input type="range" min="0" max="100" step="1" value={memoryLimit} onChange={(e) => setMemoryLimit(Number(e.target.value))} /><span className="field-help">{t("agents.detail.memoryLimitHint")}</span></div>
        </details>
      </div></section>
      <section className="settings-section"><div className="settings-copy"><h3>{t("agents.detail.capabilitiesHeading")}</h3><p>{t("agents.detail.capabilitiesCopy")}</p></div><div className="settings-fields">
        <div className="capability">
          <label className="capability-head"><input type="checkbox" checked={imageEnabled} onChange={(e) => setImageEnabled(e.target.checked)} /><ImageIcon size={17} /><span><strong>{t("agents.detail.imageLabel")}</strong><small>{t("agents.detail.imageHint")}</small></span></label>
          {imageEnabled && <label className="capability-model">{t("agents.detail.modelLabel")}<Combobox value={imageModel} onChange={setImageModel} options={IMAGE_MODELS} placeholder="gpt-4.1" allowCustom /></label>}
        </div>
        <div className="capability">
          <label className="capability-head"><input type="checkbox" checked={audioEnabled} onChange={(e) => setAudioEnabled(e.target.checked)} /><AudioLines size={17} /><span><strong>{t("agents.detail.audioLabel")}</strong><small>{t("agents.detail.audioHint")}</small></span></label>
          {audioEnabled && <label className="capability-model">{t("agents.detail.modelLabel")}<Combobox value={audioModel} onChange={setAudioModel} options={AUDIO_MODELS} placeholder="whisper-1" allowCustom /></label>}
        </div>
        <Alert type="info">{t("agents.detail.capabilitiesOpenAI")}</Alert>
      </div></section>
      <div className="sticky-save"><span>{t("agents.detail.stickyNote")}</span><button className="button primary" disabled={busy}>{busy ? <LoaderCircle className="spin" size={17} /> : <Save size={17} />} {t("agents.detail.saveConfig")}</button></div>
    </form>}


    {tab === "knowledge" && <><div className="knowledge-layout">
      <form className="panel knowledge-context" onSubmit={saveContext}><div className="panel-head"><div><h3>{t("agents.detail.manualContextHeading")}</h3><p>{t("agents.detail.manualContextCopy")}</p></div></div><textarea name="manual_context" rows={12} defaultValue={agent.manual_context} placeholder={t("agents.detail.manualContextPlaceholder")} /><div className="knowledge-actions"><small>{t("agents.detail.charsSaved", { count: agent.manual_context.length.toLocaleString("es") })}</small><button className="button secondary" disabled={busy}><Save size={16} /> {t("agents.detail.saveContext")}</button></div></form>
      <section className="panel documents-panel"><div className="panel-head"><div><h3>{t("agents.detail.pdfHeading")}</h3><p>{t("agents.detail.pdfCopy")}</p></div></div>
        <button className="dropzone" onClick={() => fileRef.current?.click()} disabled={busy}><span><UploadCloud size={24} /></span><strong>{busy ? t("agents.detail.processing") : t("agents.detail.uploadPdf")}</strong><small>{t("agents.detail.uploadHint")}</small></button><input ref={fileRef} type="file" accept="application/pdf,.pdf" hidden onChange={(e) => upload(e.target.files?.[0])} />
        <div className="documents-list">{documents.map((doc) => <div className="document-row" key={doc.id}><span className={`document-icon ${doc.status}`}><FileText size={19} /></span><div><strong>{doc.filename}</strong><small>{doc.status === "processed" ? t("agents.detail.charsExtracted", { count: doc.character_count.toLocaleString("es") }) : doc.error_message}</small></div><span className={`document-status ${doc.status}`}>{doc.status === "processed" ? <><CheckCircle2 size={14} /> {t("agents.detail.processed")}</> : <><XCircle size={14} /> {t("agents.detail.error")}</>}</span><button className="icon-button danger-icon" onClick={() => removeDocument(doc)} title={t("agents.detail.delete")}><Trash2 size={16} /></button></div>)}{!documents.length && <div className="inline-empty slim"><FileText size={22} /><div><strong>{t("agents.detail.noDocumentsTitle")}</strong><span>{t("agents.detail.noDocumentsHint")}</span></div></div>}</div>
      </section>
    </div>
    <section className="panel"><div className="panel-head"><div><h3>{t("agents.detail.qaHeading")}</h3><p>{t("agents.detail.qaCopy")}</p></div></div>
      <form className="qa-form" onSubmit={addQA}><input name="question" required placeholder={t("agents.detail.qaQuestionPlaceholder")} /><textarea name="answer" rows={2} required placeholder={t("agents.detail.qaAnswerPlaceholder")} /><button className="button secondary align-start" disabled={busy}><Plus size={15} /> {t("agents.detail.qaAdd")}</button></form>
      <div className="qa-list">{qaPairs.map((pair) => <div className="qa-item" key={pair.id}><div><strong>{pair.question}</strong><small>{pair.answer}</small></div><button type="button" className="icon-button danger-icon" onClick={() => removeQA(pair)} title={t("agents.detail.delete")}><Trash2 size={16} /></button></div>)}{!qaPairs.length && <div className="inline-empty slim"><MessageSquareText size={22} /><div><strong>{t("agents.detail.qaEmpty")}</strong></div></div>}</div>
    </section></>}

    {tab === "tools" && <AgentToolsTab agentId={id} tools={tools} onToolsChange={setTools} />}

    {tab === "widget" && <form className="settings-form" onSubmit={saveWidget}>
      <section className="settings-section"><div className="settings-copy"><h3>{t("agents.detail.widgetHeading")}</h3><p>{t("agents.detail.widgetCopy")}</p></div><div className="settings-fields">
        <label className="switch-row"><span><strong>{t("agents.detail.widgetEnable")}</strong><small>{t("agents.detail.widgetEnableHint")}</small></span><input type="checkbox" checked={widgetEnabled} onChange={(e) => setWidgetEnabled(e.target.checked)} /></label>
        <label>{t("agents.detail.widgetGreeting")}<textarea rows={2} value={widgetGreeting} onChange={(e) => setWidgetGreeting(e.target.value)} placeholder={t("agents.detail.widgetGreetingPlaceholder")} /></label>
        <div className="form-grid">
          <label>{t("agents.detail.widgetColor")}<div className="color-input"><input type="color" value={widgetColor} onChange={(e) => setWidgetColor(e.target.value)} /><input value={widgetColor} onChange={(e) => setWidgetColor(e.target.value)} /></div></label>
          <label>{t("agents.detail.widgetPosition")}<select value={widgetPosition} onChange={(e) => setWidgetPosition(e.target.value)}><option value="right">{t("agents.detail.widgetPositionRight")}</option><option value="left">{t("agents.detail.widgetPositionLeft")}</option></select></label>
        </div>
      </div></section>
      <section className="settings-section"><div className="settings-copy"><h3>{t("agents.detail.widgetEmbedHeading")}</h3><p>{t("agents.detail.widgetEmbedCopy")}</p></div><div className="settings-fields">
        {widgetEnabled ? <>
          <pre className="embed-snippet">{widgetSnippet}</pre>
          <div className="embed-actions"><button type="button" className="button secondary" onClick={() => { navigator.clipboard.writeText(widgetSnippet); toast.success(t("agents.detail.widgetCopied")); }}><Copy size={15} /> {t("agents.detail.widgetCopy2")}</button><a className="button ghost" href={`/widget/${agent.widget_public_id}`} target="_blank" rel="noreferrer"><ExternalLink size={15} /> {t("agents.detail.widgetPreview")}</a></div>
        </> : <Alert type="info">{t("agents.detail.widgetEnableFirst")}</Alert>}
      </div></section>
      <div className="sticky-save"><span>{t("agents.detail.stickyNote")}</span><button className="button primary" disabled={busy}>{busy ? <LoaderCircle className="spin" size={17} /> : <Save size={17} />} {t("agents.detail.saveConfig")}</button></div>
    </form>}

    {tab === "playground" && <ChatPlayground lockedAgentId={agent.id} />}
  </div>;
}
