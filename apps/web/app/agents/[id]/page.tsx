"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft, AudioLines, Bot, CheckCircle2, FileText, ImageIcon, LoaderCircle, MessageSquareText, Plus, Power, PowerOff, Save, Settings2, Sparkles, Trash2, UploadCloud, Wrench, XCircle } from "lucide-react";
import { api, messageFrom } from "@/lib/api";
import { useLanguage } from "@/lib/i18n";
import { businessLabel, useIndustries } from "@/lib/industries";
import { Alert } from "@/components/ui";
import { FormSkeleton } from "@/components/skeleton";
import { AiHint } from "@/components/ai-hint";
import { useToast } from "@/components/toast";
import { ChatPlayground } from "@/components/chat-playground";
import { AgentToolsTab } from "@/components/agent-tools/agent-tools-tab";
import { EscalationRulesEditor } from "@/components/escalation-rules";
import { Combobox } from "@/components/combobox";
import { PROVIDERS, modelsFor, defaultModelFor, estimateTokens, modelContextWindow, AUDIO_MODELS, IMAGE_MODELS } from "@/lib/providers";
import { narrowModels, useAvailableModels } from "@/lib/use-available-models";
import { TIMEZONES } from "@/lib/timezones";
import type { Agent, AgentTool, KnowledgeDocument, QAPair } from "@/types";

type Tab = "basics" | "knowledge" | "tools" | "playground";
const TABS: Tab[] = ["basics", "knowledge", "tools", "playground"];

export default function AgentDetailPage() {
  const { t, lang } = useLanguage();
  const available = useAvailableModels();
  const catalog = useIndustries();
  const toast = useToast();
  const { id } = useParams<{ id: string }>();
  const [agent, setAgent] = useState<Agent | null>(null);
  const [name, setName] = useState("");
  const [promptTokens, setPromptTokens] = useState<number | null>(null);
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
  const [documents, setDocuments] = useState<KnowledgeDocument[]>([]);
  const [qaPairs, setQaPairs] = useState<QAPair[]>([]);
  const [tools, setTools] = useState<AgentTool[]>([]);
  const [tab, setTab] = useState<Tab>("basics");
  const [busy, setBusy] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const load = async () => {
    const [a, d, q, tl] = await Promise.all([api<Agent>(`/agents/${id}`), api<KnowledgeDocument[]>(`/agents/${id}/documents`), api<QAPair[]>(`/agents/${id}/qa`), api<AgentTool[]>(`/agents/${id}/tools`)]);
    setAgent(a); setName(a.name); setDocuments(d); setQaPairs(q); setTools(tl);
    // What the model receives on every message, measured on the real prompt.
    api<{ prompt: string }>(`/agents/${id}/prompt`).then((r) => setPromptTokens(estimateTokens(r.prompt))).catch(() => setPromptTokens(null));
    setProvider(a.provider); setModel(a.model); setTimezone(a.timezone || "UTC");
    setTemperature(a.temperature); setMaxTokens(a.max_tokens); setMemoryLimit(a.memory_limit);
    setImageEnabled(a.image_enabled); setImageModel(a.image_model || "gpt-4.1");
    setAudioEnabled(a.audio_enabled); setAudioModel(a.audio_model || "whisper-1");
  };

  const contextWindow = modelContextWindow(model);
  const contextPct = Math.min(100, Math.round(((promptTokens ?? 0) / contextWindow) * 100));
  useEffect(() => { load(); }, [id]);
  // Let other areas deep-link straight to a tab.
  useEffect(() => { const q = new URLSearchParams(window.location.search).get("tab"); if (q === "details") setTab("basics"); else if (q && (TABS as string[]).includes(q)) setTab(q as Tab); }, []);
  // The prompt preview is what the model receives; it changes with every save,
  // so it is fetched fresh each time the tab is opened.

  async function saveConfig(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true);
    const form = new FormData(event.currentTarget);
    const payload = { name, instructions: form.get("instructions"), personality: form.get("personality"), brief_summary: form.get("brief_summary"), brief_products: form.get("brief_products"), brief_audience: form.get("brief_audience"), brief_policies: form.get("brief_policies"), brief_dos: form.get("brief_dos"), brief_donts: form.get("brief_donts"), provider, model, timezone, prompt_language: lang, temperature, max_tokens: maxTokens, memory_limit: memoryLimit, image_enabled: imageEnabled, image_model: imageModel, audio_enabled: audioEnabled, audio_model: audioModel };
    try {
      setAgent(await api<Agent>(`/agents/${id}`, { method: "PATCH", body: JSON.stringify(payload) }));
      api<{ prompt: string }>(`/agents/${id}/prompt`).then((r) => setPromptTokens(estimateTokens(r.prompt))).catch(() => {});
      toast.success(t("agents.detail.configSaved"));
    }
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
    <header className="agent-detail-head"><div className="agent-title-wrap"><span className="agent-avatar xl"><Bot size={29} /></span><div><div className="title-line"><h1>{agent.name}</h1><span className={agent.is_active ? "pill purple" : "pill"}>{agent.is_active ? t("agents.detail.published") : t("agents.detail.unpublished")}</span></div><p><Link href={`/clients/${agent.client_id}`} className="table-link">{agent.client.name}</Link>{businessLabel(catalog, agent.client, lang) ? ` · ${businessLabel(catalog, agent.client, lang)}` : ""}</p></div></div><div className="header-actions"><button className={agent.is_active ? "button ghost" : "button primary"} onClick={togglePublish} disabled={busy}>{agent.is_active ? <><PowerOff size={16} /> {t("agents.detail.unpublish")}</> : <><Power size={16} /> {t("agents.detail.publish")}</>}</button><Link href={`/playground`} className="button secondary"><MessageSquareText size={17} /> {t("agents.detail.openPlayground")}</Link></div></header>
    <nav className="tabs"><button className={tab === "basics" ? "active" : ""} onClick={() => setTab("basics")}><Settings2 size={17} /> {t("agents.detail.tabBasics")}</button><button className={tab === "knowledge" ? "active" : ""} onClick={() => setTab("knowledge")}><FileText size={17} /> {t("agents.detail.tabKnowledge")} <span>{documents.length}</span></button><button className={tab === "tools" ? "active" : ""} onClick={() => setTab("tools")}><Wrench size={17} /> {t("tools.tab")} <span>{tools.length}</span></button><button className={tab === "playground" ? "active" : ""} onClick={() => setTab("playground")}><MessageSquareText size={17} /> {t("agents.detail.tabPlayground")}</button></nav>

    {tab === "basics" && <form className="settings-form" onSubmit={saveConfig}>
      <section className="settings-section"><div className="settings-copy"><h3>{t("agents.detail.generalHeading")} <AiHint text={t("aiContext.agentName")} /></h3><p>{t("agents.detail.generalCopy")}</p></div><div className="settings-fields"><div className="form-grid"><label>{t("agents.detail.nameLabel")}<input value={name} required onChange={(e) => setName(e.target.value)} /></label><label>{t("agents.detail.clientLabel")}<input value={agent.client.name} readOnly /></label></div><p className="greeting-preview">{t("agents.detail.greetingPreview", { name: name.trim() || agent.name, client: agent.client.name })}</p></div></section>
      <section className="settings-section"><div className="settings-copy"><h3>{t("agents.detail.briefBusinessHeading")} <AiHint text={t("aiContext.agentBusiness")} /></h3><p>{t("agents.detail.briefBusinessCopy")}</p></div><div className="settings-fields">
        <label>{t("agents.detail.briefSummaryLabel")}<textarea name="brief_summary" rows={2} defaultValue={agent.brief_summary} placeholder={t("agents.detail.briefSummaryPlaceholder")} /></label>
        <div className="form-grid">
          <label>{t("agents.detail.briefProductsLabel")}<textarea name="brief_products" rows={3} defaultValue={agent.brief_products} placeholder={t("agents.detail.briefProductsPlaceholder")} /></label>
          <label>{t("agents.detail.briefAudienceLabel")}<textarea name="brief_audience" rows={3} defaultValue={agent.brief_audience} placeholder={t("agents.detail.briefAudiencePlaceholder")} /></label>
        </div>
        <label>{t("agents.detail.briefPoliciesLabel")}<textarea name="brief_policies" rows={3} defaultValue={agent.brief_policies} placeholder={t("agents.detail.briefPoliciesPlaceholder")} /><span className="field-help">{t("agents.detail.briefPoliciesHelp")}</span></label>
      </div></section>
      <section className="settings-section"><div className="settings-copy"><h3>{t("agents.detail.briefJobHeading")} <AiHint text={t("aiContext.agentJob")} /></h3><p>{t("agents.detail.briefJobCopy")}</p></div><div className="settings-fields">
        <label>{t("agents.detail.instructionsLabel")}<textarea name="instructions" rows={8} defaultValue={agent.instructions} placeholder={t("agents.detail.instructionsPlaceholder")} /></label>
        <div className="form-grid">
          <label>{t("agents.detail.briefDosLabel")}<textarea name="brief_dos" rows={3} defaultValue={agent.brief_dos} placeholder={t("agents.detail.briefDosPlaceholder")} /></label>
          <label>{t("agents.detail.briefDontsLabel")}<textarea name="brief_donts" rows={3} defaultValue={agent.brief_donts} placeholder={t("agents.detail.briefDontsPlaceholder")} /></label>
        </div>
        <span className="field-help">{t("agents.detail.briefRulesHelp")}</span>
        <label>{t("agents.detail.personalityLabel")}<textarea name="personality" rows={3} defaultValue={agent.personality} placeholder={t("agents.detail.personalityPlaceholder")} /></label>
      </div></section>
      <EscalationRulesEditor agentId={agent.id} clientId={agent.client_id} />
      <section className="settings-section"><div className="settings-copy"><h3>{t("agents.detail.aiModelHeading")}</h3><p>{t("agents.detail.aiModelCopy")}</p></div><div className="settings-fields">
        <label>{t("agents.detail.timezoneLabel")}<Combobox value={timezone} onChange={setTimezone} options={TIMEZONES} placeholder={t("agents.detail.timezoneLabel")} /></label>
        <div className="form-grid"><label>{t("agents.detail.providerLabel")}<select value={provider} onChange={(e) => { setProvider(e.target.value); if (!modelsFor(e.target.value).includes(model)) setModel(defaultModelFor(e.target.value)); }}>{PROVIDERS.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}</select></label><label>{t("agents.detail.modelLabel")}<Combobox value={model} onChange={setModel} options={narrowModels(modelsFor(provider), available?.chat?.[provider])} placeholder={t("agents.detail.modelPlaceholder")} allowCustom /></label></div>
        <div className="context-bar"><div style={{ width: `${contextPct}%` }} /><small><Sparkles size={12} /> {t("agents.detail.promptTokens", { count: (promptTokens ?? 0).toLocaleString(lang) })} · {t("agents.detail.contextUsage", { count: (promptTokens ?? 0).toLocaleString(lang), total: contextWindow.toLocaleString(lang) })}</small></div>
        <Alert type="info">{t("agents.detail.providerKeysPrefix")}<Link href="/settings">{t("agents.detail.settingsLink")}</Link>.</Alert>
        <details className="advanced-options wizard-advanced"><summary>{t("agents.detail.advancedHeading")}</summary><p className="field-help">{t("agents.detail.advancedCopy")}</p>
        <div className="slider-field"><div className="slider-head"><span>{t("agents.detail.temperatureLabel")}</span><strong>{temperature.toFixed(1)}/2</strong></div><input type="range" min="0" max="2" step="0.1" value={temperature} onChange={(e) => setTemperature(Number(e.target.value))} /><span className="field-help">{t("agents.detail.temperatureHint")}</span></div>
        <div className="slider-field"><div className="slider-head"><span>{t("agents.detail.maxTokensLabel")}</span><strong>{maxTokens}/8192</strong></div><input type="range" min="256" max="8192" step="256" value={maxTokens} onChange={(e) => setMaxTokens(Number(e.target.value))} /><span className="field-help">{t("agents.detail.maxTokensHint")}</span></div>
        <div className="slider-field"><div className="slider-head"><span>{t("agents.detail.memoryLimitLabel")}</span><strong>{memoryLimit}/100</strong></div><input type="range" min="0" max="100" step="1" value={memoryLimit} onChange={(e) => setMemoryLimit(Number(e.target.value))} /><span className="field-help">{t("agents.detail.memoryLimitHint")}</span></div>
        <div className="capabilities-intro"><strong>{t("agents.detail.capabilitiesHeading")}</strong><span className="field-help">{t("agents.detail.capabilitiesCopy")}</span></div>
        <div className="capability">
          <label className="capability-head"><input type="checkbox" checked={imageEnabled} onChange={(e) => setImageEnabled(e.target.checked)} /><ImageIcon size={17} /><span><strong>{t("agents.detail.imageLabel")}</strong><small>{t("agents.detail.imageHint")}</small></span></label>
          {imageEnabled && <label className="capability-model">{t("agents.detail.modelLabel")}<Combobox value={imageModel} onChange={setImageModel} options={narrowModels(IMAGE_MODELS, available?.image)} placeholder="gpt-4.1" allowCustom /></label>}
        </div>
        <div className="capability">
          <label className="capability-head"><input type="checkbox" checked={audioEnabled} onChange={(e) => setAudioEnabled(e.target.checked)} /><AudioLines size={17} /><span><strong>{t("agents.detail.audioLabel")}</strong><small>{t("agents.detail.audioHint")}</small></span></label>
          {audioEnabled && <label className="capability-model">{t("agents.detail.modelLabel")}<Combobox value={audioModel} onChange={setAudioModel} options={narrowModels(AUDIO_MODELS, available?.audio)} placeholder="whisper-1" allowCustom /></label>}
        </div>
        <Alert type="info">{t("agents.detail.capabilitiesOpenAI")}</Alert>
        </details>
      </div></section>
      <div className="sticky-save"><span>{t("agents.detail.stickyNote")}</span><button className="button primary" disabled={busy}>{busy ? <LoaderCircle className="spin" size={17} /> : <Save size={17} />} {t("agents.detail.saveConfig")}</button></div>
    </form>}


    {tab === "knowledge" && <div className="knowledge-stack">
      <section className="panel documents-panel"><div className="panel-head"><div><h3>{t("agents.detail.pdfHeading")}</h3><p>{t("agents.detail.pdfCopy")}</p></div></div>
        <button className="dropzone" onClick={() => fileRef.current?.click()} disabled={busy}><span><UploadCloud size={24} /></span><strong>{busy ? t("agents.detail.processing") : t("agents.detail.uploadPdf")}</strong><small>{t("agents.detail.uploadHint")}</small></button><input ref={fileRef} type="file" accept="application/pdf,.pdf" hidden onChange={(e) => upload(e.target.files?.[0])} />
        <div className="documents-list">{documents.map((doc) => <div className="document-row" key={doc.id}><span className={`document-icon ${doc.status}`}><FileText size={19} /></span><div><strong>{doc.filename}</strong><small>{doc.status === "processed" ? t("agents.detail.charsExtracted", { count: doc.character_count.toLocaleString("es") }) : doc.error_message}</small></div><span className={`document-status ${doc.status}`}>{doc.status === "processed" ? <><CheckCircle2 size={14} /> {t("agents.detail.processed")}</> : <><XCircle size={14} /> {t("agents.detail.error")}</>}</span><button className="icon-button danger-icon" onClick={() => removeDocument(doc)} title={t("agents.detail.delete")}><Trash2 size={16} /></button></div>)}{!documents.length && <div className="inline-empty slim"><FileText size={22} /><div><strong>{t("agents.detail.noDocumentsTitle")}</strong><span>{t("agents.detail.noDocumentsHint")}</span></div></div>}</div>
      </section>
    <section className="panel"><div className="panel-head"><div><h3>{t("agents.detail.qaHeading")}</h3><p>{t("agents.detail.qaCopy")}</p></div></div>
      <form className="qa-form" onSubmit={addQA}><input name="question" required placeholder={t("agents.detail.qaQuestionPlaceholder")} /><textarea name="answer" rows={2} required placeholder={t("agents.detail.qaAnswerPlaceholder")} /><button className="button secondary align-start" disabled={busy}><Plus size={15} /> {t("agents.detail.qaAdd")}</button></form>
      <div className="qa-list">{qaPairs.map((pair) => <div className="qa-item" key={pair.id}><div><strong>{pair.question}</strong><small>{pair.answer}</small></div><button type="button" className="icon-button danger-icon" onClick={() => removeQA(pair)} title={t("agents.detail.delete")}><Trash2 size={16} /></button></div>)}{!qaPairs.length && <div className="inline-empty slim"><MessageSquareText size={22} /><div><strong>{t("agents.detail.qaEmpty")}</strong></div></div>}</div>
    </section></div>}

    {tab === "tools" && <AgentToolsTab agentId={id} tools={tools} onToolsChange={setTools} />}

    {tab === "playground" && <ChatPlayground lockedAgentId={agent.id} />}
  </div>;
}
