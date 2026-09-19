"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft, AudioLines, Bot, CheckCircle2, FileText, ImageIcon, LoaderCircle, MessageSquareText, Plug, Plus, Power, PowerOff, RefreshCw, Save, Settings2, Sparkles, Trash2, UploadCloud, XCircle } from "lucide-react";
import { SectionTabs } from "@/components/section-tabs";
import { api, messageFrom } from "@/lib/api";
import { useLanguage } from "@/lib/i18n";
import { businessLabel, useIndustries } from "@/lib/industries";
import { Alert, Modal } from "@/components/ui";
import { ConfirmModal } from "@/components/confirm-modal";
import { FormSkeleton } from "@/components/skeleton";
import { AiHint } from "@/components/ai-hint";
import { useToast } from "@/components/toast";
import { ChatPlayground } from "@/components/chat-playground";
import { AgentToolsTab } from "@/components/agent-tools/agent-tools-tab";
import { EscalationRulesEditor } from "@/components/escalation-rules";
import { Combobox } from "@/components/combobox";
import { DEFAULT_PROVIDER, DEFAULT_AUDIO_MODEL, DEFAULT_EMBEDDING_MODEL, DEFAULT_IMAGE_MODEL, modelsFor, modelOptionsFor, estimateTokens, modelContextWindow, AUDIO_MODELS, EMBEDDING_MODELS, IMAGE_MODELS } from "@/lib/providers";
import { narrowModels, useAvailableModels } from "@/lib/use-available-models";
import type { Agent, AgentTool, KnowledgeDocument, QAPair, EmbeddingModelInfo } from "@/types";

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
  const [provider, setProvider] = useState<string>(DEFAULT_PROVIDER);
  const [model, setModel] = useState("");
  const [temperature, setTemperature] = useState(0.7);
  const [maxTokens, setMaxTokens] = useState(2048);
  const [memoryLimit, setMemoryLimit] = useState(30);
  const [phoneHandoverMinutes, setPhoneHandoverMinutes] = useState(10);
  const [replyDelayMin, setReplyDelayMin] = useState(6);
  const [replyDelayMax, setReplyDelayMax] = useState(9);
  const [imageEnabled, setImageEnabled] = useState(false);
  const [imageModel, setImageModel] = useState<string>(DEFAULT_IMAGE_MODEL);
  const [audioEnabled, setAudioEnabled] = useState(false);
  const [audioModel, setAudioModel] = useState<string>(DEFAULT_AUDIO_MODEL);
  const [documents, setDocuments] = useState<KnowledgeDocument[]>([]);
  const [qaPairs, setQaPairs] = useState<QAPair[]>([]);
  const [tools, setTools] = useState<AgentTool[]>([]);
  const [tab, setTab] = useState<Tab>("basics");
  const [busy, setBusy] = useState(false);
  const [indexing, setIndexing] = useState(false);
  const [embeddingModels, setEmbeddingModels] = useState<EmbeddingModelInfo[]>([]);
  const fileRef = useRef<HTMLInputElement>(null);

  const load = async () => {
    const [a, d, q, tl] = await Promise.all([api<Agent>(`/agents/${id}`), api<KnowledgeDocument[]>(`/agents/${id}/documents`), api<QAPair[]>(`/agents/${id}/qa`), api<AgentTool[]>(`/agents/${id}/tools`)]);
    setAgent(a); setName(a.name); setDocuments(d); setQaPairs(q); setTools(tl);
    // What the model receives on every message, measured on the real prompt.
    api<{ prompt: string }>(`/agents/${id}/prompt`).then((r) => setPromptTokens(estimateTokens(r.prompt))).catch(() => setPromptTokens(null));
    setProvider(a.provider); setModel(a.model);
    setTemperature(a.temperature); setMaxTokens(a.max_tokens); setMemoryLimit(a.memory_limit); setPhoneHandoverMinutes(a.phone_handover_minutes); setReplyDelayMin(a.reply_delay_min_seconds); setReplyDelayMax(a.reply_delay_max_seconds);
    setImageEnabled(a.image_enabled); setImageModel(a.image_model || DEFAULT_IMAGE_MODEL);
    setAudioEnabled(a.audio_enabled); setAudioModel(a.audio_model || DEFAULT_AUDIO_MODEL);
  };

  const contextWindow = modelContextWindow(model);
  const contextPct = Math.min(100, Math.round(((promptTokens ?? 0) / contextWindow) * 100));
  useEffect(() => { load(); }, [id]);
  useEffect(() => { api<EmbeddingModelInfo[]>("/catalog/embedding-models").then(setEmbeddingModels).catch(() => {}); }, []);

  // Mirrors MAX_FULL_CONTEXT_CHARS in the backend: at or below this the whole
  // knowledge base is sent in full and embeddings are not used.
  const FULL_CONTEXT_CHARS = 45_000;
  const smallBase = documents.reduce((sum, doc) => sum + (doc.status === "processed" ? doc.character_count : 0), 0) <= FULL_CONTEXT_CHARS;

  // Re-embed a single document with the agent's current model (repair one row).
  async function reindexOne(doc: KnowledgeDocument) {
    setIndexing(true);
    try {
      const updated = await api<KnowledgeDocument>(`/agents/${id}/documents/${doc.id}/reindex`, { method: "POST" });
      setDocuments((prev) => prev.map((d) => (d.id === updated.id ? updated : d)));
      toast.success(t("agents.detail.reindexed", { model: agent?.embedding_model || "" }));
    } catch (err) { toast.error(messageFrom(err)); } finally { setIndexing(false); }
  }

  // Re-embed every document with the agent's current model. Also the repair
  // path for uploads that were indexed without a working provider key.
  async function reindex(model?: string) {
    setIndexing(true);
    try {
      const docs = await api<KnowledgeDocument[]>(`/agents/${id}/documents/reindex`, { method: "POST" });
      setDocuments(docs);
      toast.success(t("agents.detail.reindexed", { model: model || agent?.embedding_model || "" }));
    } catch (err) { toast.error(messageFrom(err)); } finally { setIndexing(false); }
  }

  // Vectors from different models are not comparable, so a change reindexes at once.
  async function changeEmbeddingModel(model: string) {
    if (!agent || model === agent.embedding_model) return;
    setIndexing(true);
    try {
      const updated = await api<Agent>(`/agents/${id}`, { method: "PATCH", body: JSON.stringify({ embedding_model: model }) });
      setAgent(updated);
    } catch (err) { toast.error(messageFrom(err)); setIndexing(false); return; }
    await reindex(model);
  }

  // Let other areas deep-link straight to a tab.
  useEffect(() => { const q = new URLSearchParams(window.location.search).get("tab"); if (q === "details") setTab("basics"); else if (q === "integrations") setTab("tools"); else if (q && (TABS as string[]).includes(q)) setTab(q as Tab); }, []);
  // The prompt preview is what the model receives; it changes with every save,
  // so it is fetched fresh each time the tab is opened.

  async function saveConfig(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true);
    const form = new FormData(event.currentTarget);
    const payload = { name, instructions: form.get("instructions"), personality: form.get("personality"), brief_summary: form.get("brief_summary"), brief_products: form.get("brief_products"), brief_audience: form.get("brief_audience"), brief_policies: form.get("brief_policies"), brief_dos: form.get("brief_dos"), brief_donts: form.get("brief_donts"), provider, model, prompt_language: lang, temperature, max_tokens: maxTokens, memory_limit: memoryLimit, phone_handover_minutes: phoneHandoverMinutes, reply_delay_min_seconds: replyDelayMin, reply_delay_max_seconds: replyDelayMax, image_enabled: imageEnabled, image_model: imageModel, audio_enabled: audioEnabled, audio_model: audioModel };
    try {
      setAgent(await api<Agent>(`/agents/${id}`, { method: "PATCH", body: JSON.stringify(payload) }));
      api<{ prompt: string }>(`/agents/${id}/prompt`).then((r) => setPromptTokens(estimateTokens(r.prompt))).catch(() => {});
      toast.success(t("agents.detail.configSaved"));
    }
    catch (err) { toast.error(messageFrom(err)); } finally { setBusy(false); }
  }

  const router = useRouter();
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [docToDelete, setDocToDelete] = useState<KnowledgeDocument | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [deleteName, setDeleteName] = useState("");
  async function removeAgent() {
    if (!agent || deleteName.trim() !== agent.name.trim()) return;
    setBusy(true); setDeleteError(null);
    try {
      await api(`/agents/${id}`, { method: "DELETE" });
      toast.success(t("agents.detail.deletedNotice"));
      router.push(`/clients/${agent.client_id}`);
    } catch (err) { setDeleteError(messageFrom(err)); setBusy(false); }
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
    {docToDelete && <ConfirmModal title={t("agents.detail.confirmDelete", { filename: docToDelete.filename })} confirmLabel={t("agents.detail.delete")} cancelLabel={t("common.cancel")} confirmIcon={<Trash2 size={15} />} onConfirm={() => removeDocument(docToDelete)} onClose={() => setDocToDelete(null)} />}
    <Modal open={deleteOpen} title={t("agents.detail.deleteTitle", { name: agent.name })} onClose={() => setDeleteOpen(false)}>
      <div className="modal-form">
        <p className="modal-copy">{t("agents.detail.deleteCopy")}</p>
        <ul className="deletion-list">
          <li><strong>{documents.length}</strong> {t("agents.detail.deleteCountDocuments")}</li>
          <li><strong>{qaPairs.length}</strong> {t("agents.detail.deleteCountQa")}</li>
          <li><strong>{tools.length}</strong> {t("agents.detail.deleteCountTools")}</li>
        </ul>
        <p className="modal-copy">{t("agents.detail.deleteKeeps")}</p>
        <label>{t("agents.detail.deleteTypeName", { name: agent.name })}<input value={deleteName} onChange={(e) => setDeleteName(e.target.value)} autoComplete="off" placeholder={agent.name} /></label>
        {deleteError && <Alert>{deleteError}</Alert>}
        <div className="modal-actions"><button type="button" className="button" onClick={() => setDeleteOpen(false)}>{t("common.cancel")}</button><button type="button" className="button danger" disabled={busy || deleteName.trim() !== agent.name.trim()} onClick={removeAgent}>{busy ? <LoaderCircle className="spin" size={16} /> : <><Trash2 size={15} /> {t("agents.detail.deleteAgent")}</>}</button></div>
      </div>
    </Modal>
    <SectionTabs<Tab> value={tab} onChange={setTab} tabs={[
      { id: "basics", label: t("agents.detail.tabBasics"), icon: Settings2 },
      { id: "knowledge", label: t("agents.detail.tabKnowledge"), icon: FileText, badge: documents.length },
      { id: "tools", label: t("tools.tab"), icon: Plug, badge: tools.length },
      { id: "playground", label: t("agents.detail.tabPlayground"), icon: MessageSquareText },
    ]} />

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
        <label>{t("agents.detail.modelLabel")}{(() => { const allowed = narrowModels(modelsFor(provider), available?.chat?.[provider]); const known = modelOptionsFor(provider).filter((item) => allowed.includes(item.id)); const ordered = [...known.filter((item) => item.recommended), ...known.filter((item) => !item.recommended)].map((item) => item.id); const options = [...ordered, ...allowed.filter((id) => !ordered.includes(id))]; const labels = Object.fromEntries(known.map((item) => [item.id, item.label])); const tierOf = (g: string) => g === "fast" ? t("agents.wizard.modelGroupFast") : g === "balanced" ? t("agents.wizard.modelGroupBalanced") : t("agents.wizard.modelGroupCapable"); const tags = Object.fromEntries(known.map((item) => [item.id, item.recommended ? t("agents.wizard.modelBadgeRecommended") : tierOf(item.group)])); return <Combobox value={model} onChange={setModel} options={options} labels={labels} tags={tags} placeholder={t("agents.detail.modelPlaceholder")} allowCustom />; })()}</label>
        <div className="context-bar"><div style={{ width: `${contextPct}%` }} /><small><Sparkles size={12} /> {t("agents.detail.promptTokens", { count: (promptTokens ?? 0).toLocaleString(lang) })} · {t("agents.detail.contextUsage", { count: (promptTokens ?? 0).toLocaleString(lang), total: contextWindow.toLocaleString(lang) })}</small></div>
        <Alert type="info">{t("agents.detail.providerKeysPrefix")}<Link href="/settings">{t("agents.detail.settingsLink")}</Link>.</Alert>
        <details className="advanced-options wizard-advanced"><summary>{t("agents.detail.advancedHeading")}</summary><p className="field-help">{t("agents.detail.advancedCopy")}</p>
        <div className="slider-field"><div className="slider-head"><span>{t("agents.detail.temperatureLabel")}</span><strong>{temperature.toFixed(1)}/2</strong></div><input type="range" min="0" max="2" step="0.1" value={temperature} onChange={(e) => setTemperature(Number(e.target.value))} /><span className="field-help">{t("agents.detail.temperatureHint")}</span></div>
        <div className="slider-field"><div className="slider-head"><span>{t("agents.detail.maxTokensLabel")}</span><strong>{maxTokens}/8192</strong></div><input type="range" min="256" max="8192" step="256" value={maxTokens} onChange={(e) => setMaxTokens(Number(e.target.value))} /><span className="field-help">{t("agents.detail.maxTokensHint")}</span></div>
        <div className="slider-field"><div className="slider-head"><span>{t("agents.detail.memoryLimitLabel")}</span><strong>{memoryLimit}/100</strong></div><input type="range" min="0" max="100" step="1" value={memoryLimit} onChange={(e) => setMemoryLimit(Number(e.target.value))} /><span className="field-help">{t("agents.detail.memoryLimitHint")}</span></div>
        <label>{t("agents.detail.phoneHandoverLabel")}<input type="number" min="1" max="1440" required value={phoneHandoverMinutes} onChange={(e) => setPhoneHandoverMinutes(Number(e.target.value))} /><span className="field-help">{t("agents.detail.phoneHandoverHint")}</span></label>
        <div className="group-intro"><strong>{t("agents.detail.replyDelayHeading")}</strong></div>
        <div className="slider-field"><div className="slider-head"><span>{t("agents.detail.replyDelayMinLabel")} <AiHint text={t("agents.detail.replyDelayMinHint")} /></span><strong>{replyDelayMin}/60 s</strong></div><input type="range" min="0" max="60" step="1" value={replyDelayMin} onChange={(e) => { const v = Number(e.target.value); setReplyDelayMin(v); if (v > replyDelayMax) setReplyDelayMax(v); }} /></div>
        <div className="slider-field"><div className="slider-head"><span>{t("agents.detail.replyDelayMaxLabel")} <AiHint text={t("agents.detail.replyDelayMaxHint")} /></span><strong>{replyDelayMax}/60 s</strong></div><input type="range" min="0" max="60" step="1" value={replyDelayMax} onChange={(e) => { const v = Number(e.target.value); setReplyDelayMax(v); if (v < replyDelayMin) setReplyDelayMin(v); }} /></div>
        <div className="capabilities-intro"><strong>{t("agents.detail.capabilitiesHeading")}</strong><span className="field-help">{t("agents.detail.capabilitiesCopy")}</span></div>
        <div className="capability">
          <label className="capability-head"><input type="checkbox" checked={imageEnabled} onChange={(e) => setImageEnabled(e.target.checked)} /><ImageIcon size={17} /><span><strong>{t("agents.detail.imageLabel")}</strong><small>{t("agents.detail.imageHint")}</small></span></label>
          {imageEnabled && <label className="capability-model">{t("agents.detail.modelLabel")}<Combobox value={imageModel} onChange={setImageModel} options={narrowModels(IMAGE_MODELS, available?.image)} placeholder={DEFAULT_IMAGE_MODEL} allowCustom /></label>}
        </div>
        <div className="capability">
          <label className="capability-head"><input type="checkbox" checked={audioEnabled} onChange={(e) => setAudioEnabled(e.target.checked)} /><AudioLines size={17} /><span><strong>{t("agents.detail.audioLabel")}</strong><small>{t("agents.detail.audioHint")}</small></span></label>
          {audioEnabled && <label className="capability-model">{t("agents.detail.modelLabel")}<Combobox value={audioModel} onChange={setAudioModel} options={narrowModels(AUDIO_MODELS, available?.audio)} placeholder={DEFAULT_AUDIO_MODEL} allowCustom /></label>}
        </div>
        </details>
      </div></section>
      <div className="sticky-save"><div className="sticky-left"><button type="button" className="button danger" onClick={() => { setDeleteError(null); setDeleteName(""); setDeleteOpen(true); }}><Trash2 size={16} /> {t("agents.detail.deleteAgent")}</button><span>{t("agents.detail.stickyNote")}</span></div><button className="button primary" disabled={busy}>{busy ? <LoaderCircle className="spin" size={17} /> : <Save size={17} />} {t("agents.detail.saveConfig")}</button></div>
    </form>}


    {tab === "knowledge" && <div className="knowledge-stack">
      <section className="panel documents-panel"><div className="panel-head"><div><h3>{t("agents.detail.pdfHeading")}</h3><p>{t("agents.detail.pdfCopy")}</p></div></div>
        <button className="dropzone" onClick={() => fileRef.current?.click()} disabled={busy}><span><UploadCloud size={24} /></span><strong>{busy ? t("agents.detail.processing") : t("agents.detail.uploadPdf")}</strong><small>{t("agents.detail.uploadHint")}</small></button><input ref={fileRef} type="file" accept="application/pdf,.pdf" hidden onChange={(e) => upload(e.target.files?.[0])} />
        <div className="documents-list">{documents.map((doc) => <div className="document-row" key={doc.id}><span className={`document-icon ${doc.status}`}><FileText size={19} /></span><div><strong>{doc.filename}</strong><small>{doc.status === "processed" ? `${t("agents.detail.charsExtracted", { count: doc.character_count.toLocaleString("es") })} · ${smallBase ? t("agents.detail.sentInFull") : doc.chunk_count && doc.indexed_model === agent.embedding_model ? t("agents.detail.indexedChunks", { count: doc.chunk_count }) : t("agents.detail.notIndexed")}` : doc.error_message}</small></div><span className={`document-status ${doc.status}`}>{doc.status === "processed" ? <><CheckCircle2 size={14} /> {t("agents.detail.processed")}</> : <><XCircle size={14} /> {t("agents.detail.error")}</>}</span>{doc.status === "processed" && !smallBase && <button className="icon-button" onClick={() => reindexOne(doc)} disabled={indexing || busy} title={t("agents.detail.reindex")}><RefreshCw size={15} /></button>}<button className="icon-button danger-icon" onClick={() => setDocToDelete(doc)} title={t("agents.detail.delete")}><Trash2 size={16} /></button></div>)}{!documents.length && <div className="inline-empty slim"><FileText size={22} /><div><strong>{t("agents.detail.noDocumentsTitle")}</strong><span>{t("agents.detail.noDocumentsHint")}</span></div></div>}</div>
      </section>
    <section className="panel"><div className="panel-head"><div><h3>{t("agents.detail.embeddingHeading")} <AiHint text={t("aiContext.embedding")} /></h3><p>{t("agents.detail.embeddingCopy")}</p></div><button type="button" className="button secondary" onClick={() => reindex()} disabled={indexing || busy || !documents.some((doc) => doc.status === "processed")}>{indexing ? <LoaderCircle className="spin" size={15} /> : <RefreshCw size={15} />} {indexing ? t("agents.detail.reindexing") : t("agents.detail.reindex")}</button></div>
      <label className="embedding-picker">{t("agents.detail.embeddingModelLabel")}
        <select value={agent.embedding_model || DEFAULT_EMBEDDING_MODEL} disabled={indexing} onChange={(e) => changeEmbeddingModel(e.target.value)}>
          {(embeddingModels.length ? embeddingModels : narrowModels(EMBEDDING_MODELS, available?.embedding).map((id) => ({ id, label: id, input_price_per_1k: 0 } as EmbeddingModelInfo)))
            .filter((m) => !available?.embedding?.length || available.embedding.includes(m.id) || m.id === agent.embedding_model)
            .map((m) => <option key={m.id} value={m.id}>{m.label}</option>)}
          {!embeddingModels.some((m) => m.id === agent.embedding_model) && !(EMBEDDING_MODELS as readonly string[]).includes(agent.embedding_model) && <option value={agent.embedding_model}>{agent.embedding_model}</option>}
        </select>
        <span className="field-help">{t("agents.detail.embeddingHint")}</span>
      </label>
    </section>
    <section className="panel"><div className="panel-head"><div><h3>{t("agents.detail.qaHeading")}</h3><p>{t("agents.detail.qaCopy")}</p></div></div>
      <form className="qa-form" onSubmit={addQA}><input name="question" required placeholder={t("agents.detail.qaQuestionPlaceholder")} /><textarea name="answer" rows={2} required placeholder={t("agents.detail.qaAnswerPlaceholder")} /><button className="button secondary align-start" disabled={busy}><Plus size={15} /> {t("agents.detail.qaAdd")}</button></form>
      <div className="qa-list">{qaPairs.map((pair) => <div className="qa-item" key={pair.id}><div><strong>{pair.question}</strong><small>{pair.answer}</small></div><button type="button" className="icon-button danger-icon" onClick={() => removeQA(pair)} title={t("agents.detail.delete")}><Trash2 size={16} /></button></div>)}{!qaPairs.length && <div className="inline-empty slim"><MessageSquareText size={22} /><div><strong>{t("agents.detail.qaEmpty")}</strong></div></div>}</div>
    </section></div>}

    {tab === "tools" && <AgentToolsTab agentId={id} tools={tools} onToolsChange={setTools} />}

    {tab === "playground" && <ChatPlayground lockedAgentId={agent.id} />}
  </div>;
}
