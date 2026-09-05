"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, ArrowRight, AudioLines, Check, ImageIcon, LoaderCircle, PencilLine, Sparkles } from "lucide-react";
import { Alert } from "@/components/ui";
import { useToast } from "@/components/toast";
import { api, messageFrom } from "@/lib/api";
import { useLanguage } from "@/lib/i18n";
import { PROVIDERS, modelsFor, modelOptionsFor, defaultModelFor, estimateTokens } from "@/lib/providers";
import { narrowModels, useAvailableModels } from "@/lib/use-available-models";
import { Combobox } from "@/components/combobox";
import { TIMEZONES } from "@/lib/timezones";
import { agentTemplates, localize } from "@/lib/agent-templates";
import type { Agent, Client } from "@/types";

const BROWSER_TZ = (() => {
  try { return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC"; } catch { return "UTC"; }
})();

const STEP_KEYS = ["agents.wizard.s1", "agents.wizard.s2", "agents.wizard.s3", "agents.wizard.s4", "agents.wizard.s5"] as const;

export default function NewAgentPage() {
  const { t, lang } = useLanguage();
  const available = useAvailableModels();
  const toast = useToast();
  const router = useRouter();
  const [step, setStepState] = useState(0);
  const [reached, setReached] = useState(0);
  const setStep = (next: number | ((s: number) => number)) => setStepState((s) => { const value = typeof next === "function" ? next(s) : next; setReached((r) => Math.max(r, value)); return value; });
  const [clients, setClients] = useState<Client[]>([]);
  const [busy, setBusy] = useState(false);

  const [templateId, setTemplateId] = useState("");
  const [clientId, setClientId] = useState("");
  const [name, setName] = useState("");
  const [instructions, setInstructions] = useState("");
  const [personality, setPersonality] = useState("");
  const [brief, setBrief] = useState({ summary: "", products: "", audience: "", policies: "", dos: "", donts: "" });
  const [provider, setProvider] = useState("openai");
  const [model, setModel] = useState(defaultModelFor("openai"));
  const [timezone, setTimezone] = useState(BROWSER_TZ);
  const [temperature, setTemperature] = useState(0.7);
  const [maxTokens, setMaxTokens] = useState(2048);
  const [memoryLimit, setMemoryLimit] = useState(30);
  // Multimodal understanding is on unless the user switches it off here.
  const [imageEnabled, setImageEnabled] = useState(true);
  const [audioEnabled, setAudioEnabled] = useState(true);

  useEffect(() => {
    const preferred = new URLSearchParams(window.location.search).get("client") || "";
    api<Client[]>("/clients").then((c) => {
      setClients(c);
      setClientId(preferred || c[0]?.id || "");
    }).catch(() => {});
  }, []);

  const promptTokens = useMemo(() => estimateTokens([brief.summary, brief.products, brief.audience, brief.policies, instructions, brief.dos, brief.donts, personality].join("\n")), [brief, instructions, personality]);

  function applyTemplate(id: string) {
    setTemplateId(id);
    const tpl = agentTemplates.find((item) => item.id === id);
    if (tpl) {
      setInstructions(localize(tpl.instructions, lang));
      setPersonality(localize(tpl.personality, lang));
      setBrief({ summary: localize(tpl.brief.summary, lang), products: localize(tpl.brief.products, lang), audience: localize(tpl.brief.audience, lang), policies: localize(tpl.brief.policies, lang), dos: localize(tpl.brief.dos, lang), donts: localize(tpl.brief.donts, lang) });
    } else {
      setInstructions(""); setPersonality("");
      setBrief({ summary: "", products: "", audience: "", policies: "", dos: "", donts: "" });
    }
    setStep(1);
  }

  const canNext = step === 1 ? name.trim().length > 0 && Boolean(clientId) : true;

  async function create() {
    setBusy(true);
    try {
      const agent = await api<Agent>("/agents", { method: "POST", body: JSON.stringify({
        client_id: clientId, name, instructions, personality,
        brief_summary: brief.summary, brief_products: brief.products, brief_audience: brief.audience, brief_policies: brief.policies, brief_dos: brief.dos, brief_donts: brief.donts,
        provider, model: model || "", timezone, prompt_language: lang,
        temperature, max_tokens: maxTokens, memory_limit: memoryLimit, is_active: true,
        image_enabled: imageEnabled, audio_enabled: audioEnabled,
      }) });
      router.push(`/agents/${agent.id}`);
    } catch (err) { toast.error(messageFrom(err)); setBusy(false); }
  }

  if (!clients.length) {
    return <div className="page narrow-page">
      <Link href="/agents" className="back-link"><ArrowLeft size={17} /> {t("agents.new.back")}</Link>
      <Alert type="info">{t("agents.new.needClient")} <Link href="/clients/new">{t("agents.new.createClient")}</Link></Alert>
    </div>;
  }

  return <div className="page narrow-page">
    <Link href="/agents" className="back-link"><ArrowLeft size={17} /> {t("agents.new.back")}</Link>
    <header className="wizard-head"><span className="eyebrow">{t("agents.new.eyebrow")}</span><h1>{t("agents.new.title")}</h1></header>

    <ol className="wizard-steps">
      {STEP_KEYS.map((key, index) => { const reachable = index <= reached && (index <= 1 || (name.trim().length > 0 && Boolean(clientId))); return (
        <li key={key} className={`${index === step ? "current" : index < step ? "done" : ""}${reachable && index !== step ? " clickable" : ""}`} onClick={() => reachable && !busy && setStep(index)} role={reachable ? "button" : undefined} tabIndex={reachable && index !== step ? 0 : undefined} onKeyDown={(e) => { if (reachable && (e.key === "Enter" || e.key === " ")) setStep(index); }}>
          <span>{index < step ? <Check size={14} /> : index + 1}</span>
          <small>{t(key)}</small>
        </li>
      ); })}
    </ol>

    <section className="wizard-card">
      {step === 0 && <div className="wizard-templates">
        <div className="wizard-copy"><h2>{t("agents.wizard.templatesTitle")}</h2><p>{t("agents.wizard.templatesSubtitle")}</p></div>
        <div className="template-grid">
          {agentTemplates.map((tpl) => (
            <button type="button" key={tpl.id} className={`template-card ${templateId === tpl.id ? "active" : ""}`} onClick={() => applyTemplate(tpl.id)}>
              <span className="template-icon"><tpl.icon size={20} /></span>
              <strong>{localize(tpl.name, lang)}</strong>
              <small>{localize(tpl.tagline, lang)}</small>
            </button>
          ))}
          <button type="button" className={`template-card blank ${templateId === "" ? "active" : ""}`} onClick={() => { applyTemplate(""); }}>
            <span className="template-card-top"><span className="template-icon"><PencilLine size={20} /></span><em className="template-badge">{t("agents.wizard.modelBadgeRecommended")}</em></span>
            <strong>{t("agents.wizard.blankName")}</strong>
            <small>{t("agents.wizard.blankTagline")}</small>
          </button>
        </div>
      </div>}

      {step === 1 && <div className="wizard-fields">
        <div className="wizard-copy"><h2>{t("agents.wizard.identityTitle")}</h2><p>{t("agents.wizard.identitySubtitle")}</p></div>
        <div className="form-grid">
          <label>{t("agents.new.clientLabel")}<select value={clientId} onChange={(e) => setClientId(e.target.value)}>{clients.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></label>
          <label>{t("agents.new.nameLabel")}<input value={name} onChange={(e) => setName(e.target.value)} required autoFocus placeholder={t("agents.new.namePlaceholder")} /></label>
        </div>
        {name.trim() && <p className="greeting-preview">{t("agents.detail.greetingPreview", { name: name.trim(), client: clients.find((c) => c.id === clientId)?.name || "" })}</p>}
      </div>}

      {step === 2 && <div className="wizard-fields">
        <div className="wizard-copy"><h2>{t("agents.wizard.essentialsTitle")}</h2><p>{t("agents.wizard.essentialsSubtitle")}</p></div>
        <label>{t("agents.detail.briefSummaryLabel")}<textarea value={brief.summary} onChange={(e) => setBrief({ ...brief, summary: e.target.value })} rows={2} autoFocus placeholder={t("agents.detail.briefSummaryPlaceholder")} /></label>
        <label>{t("agents.detail.briefPoliciesLabel")}<textarea value={brief.policies} onChange={(e) => setBrief({ ...brief, policies: e.target.value })} rows={3} placeholder={t("agents.detail.briefPoliciesPlaceholder")} /></label>
        <label>{t("agents.new.instructionsLabel")}<textarea value={instructions} onChange={(e) => setInstructions(e.target.value)} rows={5} placeholder={t("agents.new.instructionsPlaceholder")} /></label>
        <span className="field-help">{t("agents.wizard.essentialsLater")}</span>
      </div>}

      {step === 3 && <div className="wizard-fields">
        <div className="wizard-copy"><h2>{t("agents.wizard.modelTitle")}</h2><p>{t("agents.wizard.modelSubtitle")}</p></div>
        <label>{t("agents.new.providerLabel")}<select value={provider} onChange={(e) => { setProvider(e.target.value); setModel(defaultModelFor(e.target.value)); }}>{PROVIDERS.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}</select></label>
        <label>{t("agents.new.modelLabel")}{(() => { const allowed = narrowModels(modelsFor(provider), available?.chat?.[provider]); const catalog = modelOptionsFor(provider); const known = catalog.filter((item) => allowed.includes(item.id)); const ordered = [...known.filter((item) => item.recommended), ...known.filter((item) => !item.recommended)].map((item) => item.id); const options = [...ordered, ...allowed.filter((id) => !ordered.includes(id))]; const labels = Object.fromEntries(known.map((item) => [item.id, item.label])); const tierOf = (g: string) => g === "fast" ? t("agents.wizard.modelGroupFast") : g === "balanced" ? t("agents.wizard.modelGroupBalanced") : t("agents.wizard.modelGroupCapable"); const tags = Object.fromEntries(known.map((item) => [item.id, item.recommended ? t("agents.wizard.modelBadgeRecommended") : tierOf(item.group)])); return <Combobox value={model} onChange={setModel} options={options} labels={labels} tags={tags} placeholder={t("agents.new.modelPlaceholder")} allowCustom />; })()}</label>
        <label>{t("agents.detail.timezoneLabel")}<Combobox value={timezone} onChange={setTimezone} options={TIMEZONES} placeholder={t("agents.detail.timezoneLabel")} /></label>
        <details className="advanced-options wizard-advanced"><summary>{t("agents.detail.advancedHeading")}</summary><p className="field-help">{t("agents.detail.advancedCopy")}</p>
        <div className="slider-field"><div className="slider-head"><span>{t("agents.detail.temperatureLabel")}</span><strong>{temperature.toFixed(1)}/2</strong></div><input type="range" min="0" max="2" step="0.1" value={temperature} onChange={(e) => setTemperature(Number(e.target.value))} /><span className="field-help">{t("agents.detail.temperatureHint")}</span></div>
        <div className="slider-field"><div className="slider-head"><span>{t("agents.detail.maxTokensLabel")}</span><strong>{maxTokens}/8192</strong></div><input type="range" min="256" max="8192" step="256" value={maxTokens} onChange={(e) => setMaxTokens(Number(e.target.value))} /><span className="field-help">{t("agents.detail.maxTokensHint")}</span></div>
        <div className="slider-field"><div className="slider-head"><span>{t("agents.detail.memoryLimitLabel")}</span><strong>{memoryLimit}/100</strong></div><input type="range" min="0" max="100" step="1" value={memoryLimit} onChange={(e) => setMemoryLimit(Number(e.target.value))} /><span className="field-help">{t("agents.detail.memoryLimitHint")}</span></div>
        <div className="capabilities-intro"><strong>{t("agents.detail.capabilitiesHeading")}</strong><span className="field-help">{t("agents.detail.capabilitiesCopy")}</span></div>
        <div className="capability"><label className="capability-head"><input type="checkbox" checked={imageEnabled} onChange={(e) => setImageEnabled(e.target.checked)} /><ImageIcon size={17} /><span><strong>{t("agents.detail.imageLabel")}</strong><small>{t("agents.detail.imageHint")}</small></span></label></div>
        <div className="capability"><label className="capability-head"><input type="checkbox" checked={audioEnabled} onChange={(e) => setAudioEnabled(e.target.checked)} /><AudioLines size={17} /><span><strong>{t("agents.detail.audioLabel")}</strong><small>{t("agents.detail.audioHint")}</small></span></label></div>
        </details>
      </div>}

      {step === 4 && <div className="wizard-fields">
        <div className="wizard-copy"><h2>{t("agents.wizard.reviewTitle")}</h2><p>{t("agents.wizard.reviewSubtitle")}</p></div>
        <dl className="review-list">
          <div><dt>{t("agents.new.nameLabel")}</dt><dd>{name}</dd></div>
          <div><dt>{t("agents.new.clientLabel")}</dt><dd>{clients.find((c) => c.id === clientId)?.name || ""}</dd></div>
          <div><dt>{t("agents.wizard.reviewTemplate")}</dt><dd>{templateId ? localize(agentTemplates.find((x) => x.id === templateId)!.name, lang) : t("agents.wizard.blankName")}</dd></div>
          <div><dt>{t("agents.detail.briefSummaryLabel")}</dt><dd>{brief.summary.trim() || <span className="muted">{t("agents.wizard.reviewEmpty")}</span>}</dd></div>
          <div><dt>{t("agents.new.providerLabel")}</dt><dd>{PROVIDERS.find((p) => p.id === provider)?.label || provider}</dd></div>
          <div><dt>{t("agents.new.modelLabel")}</dt><dd>{modelOptionsFor(provider).find((item) => item.id === model)?.label || model}</dd></div>
          <div><dt>{t("agents.wizard.reviewPrompt")}</dt><dd><span className="token-pill"><Sparkles size={13} /> {t("agents.wizard.tokens", { count: promptTokens.toLocaleString(lang) })}</span></dd></div>
        </dl>
      </div>}
    </section>

    <div className="wizard-nav">
      <button className="button secondary" onClick={() => setStep((s) => Math.max(0, s - 1))} disabled={step === 0 || busy}><ArrowLeft size={16} /> {t("agents.wizard.back")}</button>
      <span className="wizard-progress">{t("agents.wizard.stepOf", { n: step + 1, total: STEP_KEYS.length })}</span>
      {step < STEP_KEYS.length - 1
        ? <button className="button primary" onClick={() => canNext && setStep((s) => s + 1)} disabled={!canNext}>{t("agents.wizard.next")} <ArrowRight size={16} /></button>
        : <button className="button primary" onClick={create} disabled={busy || !name.trim()}>{busy ? <LoaderCircle className="spin" size={16} /> : <Check size={16} />} {t("agents.new.createAgent")}</button>}
    </div>
  </div>;
}
