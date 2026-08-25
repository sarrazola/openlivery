"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, ArrowRight, Check, LoaderCircle, PencilLine, Sparkles } from "lucide-react";
import { Alert } from "@/components/ui";
import { useToast } from "@/components/toast";
import { api, messageFrom } from "@/lib/api";
import { useLanguage } from "@/lib/i18n";
import { PROVIDERS, modelsFor, modelOptionsFor, defaultModelFor, estimateTokens } from "@/lib/providers";
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
  const toast = useToast();
  const router = useRouter();
  const [step, setStep] = useState(0);
  const [clients, setClients] = useState<Client[]>([]);
  const [busy, setBusy] = useState(false);

  const [templateId, setTemplateId] = useState("");
  const [clientId, setClientId] = useState("");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [instructions, setInstructions] = useState("");
  const [personality, setPersonality] = useState("");
  const [provider, setProvider] = useState("openai");
  const [model, setModel] = useState(defaultModelFor("openai"));
  const [timezone, setTimezone] = useState(BROWSER_TZ);
  const [temperature, setTemperature] = useState(0.7);
  const [maxTokens, setMaxTokens] = useState(2048);
  const [memoryLimit, setMemoryLimit] = useState(30);

  useEffect(() => {
    const preferred = new URLSearchParams(window.location.search).get("client") || "";
    api<Client[]>("/clients").then((c) => {
      setClients(c);
      setClientId(preferred || c[0]?.id || "");
    }).catch(() => {});
  }, []);

  const promptTokens = useMemo(() => estimateTokens([description, instructions, personality].join("\n")), [description, instructions, personality]);

  function applyTemplate(id: string) {
    setTemplateId(id);
    const tpl = agentTemplates.find((item) => item.id === id);
    if (tpl) {
      setDescription(localize(tpl.description, lang));
      setInstructions(localize(tpl.instructions, lang));
      setPersonality(localize(tpl.personality, lang));
    }
    setStep(1);
  }

  const canNext = step === 1 ? name.trim().length > 0 && Boolean(clientId) : step === 3 ? model.trim().length > 0 : true;

  async function create() {
    setBusy(true);
    try {
      const agent = await api<Agent>("/agents", { method: "POST", body: JSON.stringify({
        client_id: clientId, name, description, instructions, personality,
        provider, model: model || "", timezone,
        temperature, max_tokens: maxTokens, memory_limit: memoryLimit, is_active: true,
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
      {STEP_KEYS.map((key, index) => (
        <li key={key} className={index === step ? "current" : index < step ? "done" : ""}>
          <span>{index < step ? <Check size={14} /> : index + 1}</span>
          <small>{t(key)}</small>
        </li>
      ))}
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
          <button type="button" className="template-card blank" onClick={() => { setTemplateId(""); setStep(1); }}>
            <span className="template-icon"><PencilLine size={20} /></span>
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
        <label>{t("agents.new.descriptionLabel")}<textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={3} placeholder={t("agents.new.descriptionPlaceholder")} /></label>
      </div>}

      {step === 2 && <div className="wizard-fields">
        <div className="wizard-copy"><h2>{t("agents.wizard.promptTitle")}</h2><p>{t("agents.wizard.promptSubtitle")}</p></div>
        <label>{t("agents.new.instructionsLabel")}<textarea value={instructions} onChange={(e) => setInstructions(e.target.value)} rows={10} placeholder={t("agents.new.instructionsPlaceholder")} /></label>
        <label>{t("agents.new.personalityLabel")}<textarea value={personality} onChange={(e) => setPersonality(e.target.value)} rows={3} placeholder={t("agents.new.personalityPlaceholder")} /></label>
        <div className="token-meter"><span><Sparkles size={13} /> {t("agents.wizard.tokens", { count: promptTokens.toLocaleString(lang) })}</span><small className="field-help">{t("agents.wizard.tokensHint")}</small></div>
      </div>}

      {step === 3 && <div className="wizard-fields">
        <div className="wizard-copy"><h2>{t("agents.wizard.modelTitle")}</h2><p>{t("agents.wizard.modelSubtitle")}</p></div>
        <label>{t("agents.detail.timezoneLabel")}<Combobox value={timezone} onChange={setTimezone} options={TIMEZONES} placeholder={t("agents.detail.timezoneLabel")} /></label>
        <label>{t("agents.new.providerLabel")}<select value={provider} onChange={(e) => { setProvider(e.target.value); setModel(defaultModelFor(e.target.value)); }}>{PROVIDERS.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}</select></label>
        <div className="field-block">
          <span className="field-label">{t("agents.new.modelLabel")}</span>
          {(["fast", "balanced", "capable"] as const).map((group) => { const options = modelOptionsFor(provider).filter((item) => item.group === group); if (!options.length) return null; return <div className="model-group" key={group}><div className="model-group-head"><span className="field-label">{t(`agents.wizard.modelGroup${group === "fast" ? "Fast" : group === "balanced" ? "Balanced" : "Capable"}`)}</span><small>{t(`agents.wizard.modelNote${group === "fast" ? "Fast" : group === "balanced" ? "Balanced" : "Capable"}`)}</small></div><div className="model-recommendations">{options.map((option) => <button type="button" key={option.id} className={option.id === model ? "active" : ""} onClick={() => setModel(option.id)}><span><strong>{option.label}</strong>{option.recommended && <em>{t("agents.wizard.modelBadgeRecommended")}</em>}</span><code>{option.id}</code></button>)}</div></div>; })}
          <details className="advanced-options wizard-advanced"><summary>{t("agents.wizard.modelShowAll")}</summary><Combobox value={model} onChange={setModel} options={modelsFor(provider)} placeholder={t("agents.new.modelPlaceholder")} allowCustom /></details>
          <span className="field-help">{t("agents.wizard.modelHelp")}</span>
        </div>
        <details className="advanced-options wizard-advanced"><summary>{t("agents.detail.advancedHeading")}</summary><p className="field-help">{t("agents.detail.advancedCopy")}</p>
        <div className="slider-field"><div className="slider-head"><span>{t("agents.detail.temperatureLabel")}</span><strong>{temperature.toFixed(1)}/2</strong></div><input type="range" min="0" max="2" step="0.1" value={temperature} onChange={(e) => setTemperature(Number(e.target.value))} /><span className="field-help">{t("agents.detail.temperatureHint")}</span></div>
        <div className="slider-field"><div className="slider-head"><span>{t("agents.detail.maxTokensLabel")}</span><strong>{maxTokens}/8192</strong></div><input type="range" min="256" max="8192" step="256" value={maxTokens} onChange={(e) => setMaxTokens(Number(e.target.value))} /><span className="field-help">{t("agents.detail.maxTokensHint")}</span></div>
        <div className="slider-field"><div className="slider-head"><span>{t("agents.detail.memoryLimitLabel")}</span><strong>{memoryLimit}/100</strong></div><input type="range" min="0" max="100" step="1" value={memoryLimit} onChange={(e) => setMemoryLimit(Number(e.target.value))} /><span className="field-help">{t("agents.detail.memoryLimitHint")}</span></div>
        </details>
      </div>}

      {step === 4 && <div className="wizard-fields">
        <div className="wizard-copy"><h2>{t("agents.wizard.reviewTitle")}</h2><p>{t("agents.wizard.reviewSubtitle")}</p></div>
        <dl className="review-list">
          <div><dt>{t("agents.new.nameLabel")}</dt><dd>{name || <span className="muted">—</span>}</dd></div>
          <div><dt>{t("agents.new.clientLabel")}</dt><dd>{clients.find((c) => c.id === clientId)?.name || "—"}</dd></div>
          <div><dt>{t("agents.wizard.reviewTemplate")}</dt><dd>{templateId ? localize(agentTemplates.find((x) => x.id === templateId)!.name, lang) : t("agents.wizard.blankName")}</dd></div>
          <div><dt>{t("agents.new.providerLabel")}</dt><dd>{PROVIDERS.find((p) => p.id === provider)?.label || provider}</dd></div>
          <div><dt>{t("agents.new.modelLabel")}</dt><dd>{model || <span className="muted">{t("agents.wizard.modelRequired")}</span>}</dd></div>
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
