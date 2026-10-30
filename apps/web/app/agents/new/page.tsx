"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, ArrowRight, AudioLines, Check, ChevronLeft, ChevronRight, ImageIcon, LoaderCircle, PencilLine, Phone, Sparkles } from "lucide-react";
import { Alert } from "@/components/ui";
import { useToast } from "@/components/toast";
import { api, messageFrom } from "@/lib/api";
import { useLanguage, type I18nKey } from "@/lib/i18n";
import { DEFAULT_PROVIDER, modelsFor, modelOptionsFor, defaultModelFor, estimateTokens } from "@/lib/providers";
import { narrowModels, useAvailableModels } from "@/lib/use-available-models";
import { Combobox } from "@/components/combobox";
import { agentTemplates, localize } from "@/lib/agent-templates";
import { VoiceModelPicker } from "@/components/voice-model-picker";
import { VoicePicker } from "@/components/voice-picker";
import type { Agent, AgentKind, Client } from "@/types";
import { AiHint } from "@/components/ai-hint";

type Step = "template" | "voice" | "identity" | "essentials" | "model" | "review";
// A chat agent starts from a template; a voice agent starts from its voice,
// and its light model is settled on the review instead of a step of its own.
const STEPS: Record<AgentKind, Step[]> = {
  chat: ["template", "identity", "essentials", "model", "review"],
  voice: ["voice", "identity", "essentials", "review"],
};
const STEP_LABELS: Record<Step, I18nKey> = {
  template: "agents.wizard.s1", voice: "phone.agent.stepVoice", identity: "agents.wizard.s2",
  essentials: "agents.wizard.s3", model: "agents.wizard.s4", review: "agents.wizard.s5",
};
// On a call every second of thinking is heard: voice agents start on a light model.
const VOICE_MODEL = "eleven_realtime_v1_mini";

export default function NewAgentPage() {
  const { t, lang } = useLanguage();
  const available = useAvailableModels();
  const toast = useToast();
  const router = useRouter();
  // Read from the address (?kind=voice) before anything renders.
  const [kind, setKind] = useState<AgentKind | null>(null);
  const [step, setStepState] = useState(0);
  const [reached, setReached] = useState(0);
  const setStep = (next: number | ((s: number) => number)) => setStepState((s) => { const value = typeof next === "function" ? next(s) : next; setReached((r) => Math.max(r, value)); return value; });
  const [clients, setClients] = useState<Client[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState(false);

  const [templateId, setTemplateId] = useState("");
  const [clientId, setClientId] = useState("");
  const [name, setName] = useState("");
  const [instructions, setInstructions] = useState("");
  const [personality, setPersonality] = useState("");
  const [brief, setBrief] = useState({ summary: "", products: "", audience: "", policies: "", dos: "", donts: "" });
  const provider = DEFAULT_PROVIDER;
  const [model, setModel] = useState(defaultModelFor(provider));
  const [temperature, setTemperature] = useState(0.7);
  const [maxTokens, setMaxTokens] = useState(2048);
  const [memoryLimit, setMemoryLimit] = useState(30);
  const [phoneHandoverMinutes, setPhoneHandoverMinutes] = useState(10);
  const [replyDelayMin, setReplyDelayMin] = useState(6);
  const [replyDelayMax, setReplyDelayMax] = useState(9);
  // Multimodal understanding is on unless the user switches it off here.
  const [imageEnabled, setImageEnabled] = useState(true);
  const [audioEnabled, setAudioEnabled] = useState(true);
  const [voice, setVoice] = useState<{ id: string; name: string }>({ id: "", name: "" });
  const [greeting, setGreeting] = useState("");

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const wanted: AgentKind = params.get("kind") === "voice" ? "voice" : "chat";
    setKind(wanted);
    if (wanted === "voice") setModel(VOICE_MODEL);
    const preferred = params.get("client") || "";
    api<Client[]>("/clients").then((c) => {
      setClients(c);
      setClientId(preferred || c[0]?.id || "");
    }).catch(() => {}).finally(() => setLoaded(true));
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

  // Nothing until the address and the clients are read: no flash of "create a client first".
  if (!kind || !loaded) return <div className="page narrow-page" />;
  const steps = STEPS[kind];
  const current = steps[step];
  const identityDone = name.trim().length > 0 && Boolean(clientId);
  const voiceDone = Boolean(voice.id) && greeting.trim().length > 0;
  const canNext = current === "identity" ? identityDone : current === "voice" ? voiceDone : true;
  // A step is open once visited, and past the identity only with a name and a client.
  const identityIndex = steps.indexOf("identity");
  const reachable = (index: number) => index >= 0 && index < steps.length && index <= reached && (index <= identityIndex || identityDone) && (kind === "chat" || index === 0 || voiceDone);

  async function create() {
    setBusy(true);
    const voiceAgent = kind === "voice";
    try {
      const agent = await api<Agent>("/agents", { method: "POST", body: JSON.stringify({
        client_id: clientId, name, instructions, personality,
        brief_summary: brief.summary, brief_products: brief.products, brief_audience: brief.audience, brief_policies: brief.policies, brief_dos: brief.dos, brief_donts: brief.donts,
        provider, model: model || "", prompt_language: lang,
        temperature, max_tokens: maxTokens, memory_limit: memoryLimit, phone_handover_minutes: phoneHandoverMinutes, reply_delay_min_seconds: replyDelayMin, reply_delay_max_seconds: replyDelayMax, is_active: true,
        image_enabled: !voiceAgent && imageEnabled, audio_enabled: !voiceAgent && audioEnabled,
        kind, voice_id: voiceAgent ? voice.id : "", voice_name: voiceAgent ? voice.name : "", greeting: voiceAgent ? greeting.trim() : "",
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

  const modelPicker = (() => { const allowed = narrowModels(modelsFor(provider), available?.chat?.[provider]); const catalog = modelOptionsFor(provider); const known = catalog.filter((item) => allowed.includes(item.id)); const ordered = [...known.filter((item) => item.recommended), ...known.filter((item) => !item.recommended)].map((item) => item.id); const options = [...ordered, ...allowed.filter((id) => !ordered.includes(id))]; const labels = Object.fromEntries(known.map((item) => [item.id, item.label])); const tierOf = (g: string) => g === "fast" ? t("agents.wizard.modelGroupFast") : g === "balanced" ? t("agents.wizard.modelGroupBalanced") : t("agents.wizard.modelGroupCapable"); const tags = Object.fromEntries(known.map((item) => [item.id, item.recommended ? t("agents.wizard.modelBadgeRecommended") : tierOf(item.group)])); return <Combobox value={model} onChange={setModel} options={options} labels={labels} tags={tags} placeholder={t("agents.new.modelPlaceholder")} allowCustom />; })();
  const sampling = <>
    <div className="slider-field"><div className="slider-head"><span>{t("agents.detail.temperatureLabel")}</span><strong>{temperature.toFixed(1)}/2</strong></div><input type="range" min="0" max="2" step="0.1" value={temperature} onChange={(e) => setTemperature(Number(e.target.value))} /><span className="field-help">{t("agents.detail.temperatureHint")}</span></div>
    <div className="slider-field"><div className="slider-head"><span>{t("agents.detail.maxTokensLabel")}</span><strong>{maxTokens}/8192</strong></div><input type="range" min="256" max="8192" step="256" value={maxTokens} onChange={(e) => setMaxTokens(Number(e.target.value))} /><span className="field-help">{t("agents.detail.maxTokensHint")}</span></div>
    <div className="slider-field"><div className="slider-head"><span>{t("agents.detail.memoryLimitLabel")}</span><strong>{memoryLimit}/100</strong></div><input type="range" min="0" max="100" step="1" value={memoryLimit} onChange={(e) => setMemoryLimit(Number(e.target.value))} /><span className="field-help">{t("agents.detail.memoryLimitHint")}</span></div>
  </>;

  return <div className={`page narrow-page${kind === "voice" ? " voice-wizard" : ""}`}>
    <Link href="/agents" className="back-link"><ArrowLeft size={17} /> {t("agents.new.back")}</Link>
    {kind === "voice"
      ? <header className="wizard-head"><span className="eyebrow"><Phone size={13} /> {t("phone.agent.newEyebrow")}</span><h1>{t("phone.agent.newTitle")}</h1></header>
      : <header className="wizard-head"><span className="eyebrow">{t("agents.new.eyebrow")}</span><h1>{t("agents.new.title")}</h1></header>}

    <ol className="wizard-steps">
      {steps.map((key, index) => { const open = reachable(index); return (
        <li key={key} className={`${index === step ? "current" : index < step ? "done" : ""}${open && index !== step ? " clickable" : ""}`} onClick={() => open && !busy && setStep(index)} role={open ? "button" : undefined} tabIndex={open && index !== step ? 0 : undefined} onKeyDown={(e) => { if (open && (e.key === "Enter" || e.key === " ")) setStep(index); }}>
          <span>{index < step ? <Check size={14} /> : index + 1}</span>
          <small>{t(STEP_LABELS[key])}</small>
        </li>
      ); })}
    </ol>
    {/* Phone stand-in for the step pills (the stylesheet swaps one for the
        other): one step at a time, under the same reachability rule the pills
        enforce, so the arrows can never skip a step the footer would refuse. */}
    <div className="section-pager wizard-pager">
      <button type="button" className="button ghost" disabled={step === 0 || busy} aria-label={t("agents.wizard.back")} onClick={() => setStep((s) => Math.max(0, s - 1))}><ChevronLeft size={18} /></button>
      <div className="section-pager-current"><span>{step + 1}</span><strong>{t(STEP_LABELS[current])}</strong><small>{step + 1} / {steps.length}</small></div>
      <button type="button" className="button ghost" disabled={busy || step >= steps.length - 1 || !(reachable(step + 1) || canNext)} aria-label={t("agents.wizard.next")} onClick={() => setStep((s) => Math.min(steps.length - 1, s + 1))}><ChevronRight size={18} /></button>
    </div>

    <section className="wizard-card">
      {current === "template" && <div className="wizard-templates">
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

      {current === "voice" && <div className="wizard-fields">
        <div className="wizard-copy"><h2>{t("phone.agent.stepVoiceTitle")}</h2><p>{t("phone.agent.stepVoiceSubtitle")}</p></div>
        <VoicePicker value={voice.id} name={voice.name} onChange={setVoice} />
        <label>{t("phone.channel.greetingLabel")}<textarea rows={2} maxLength={600} value={greeting} placeholder={t("phone.channel.greetingPlaceholder")} onChange={(e) => setGreeting(e.target.value)} /></label>
        <span className="field-help">{t("phone.channel.greetingHint")}</span>
      </div>}

      {current === "identity" && <div className="wizard-fields">
        <div className="wizard-copy"><h2>{t("agents.wizard.identityTitle")}</h2><p>{t("agents.wizard.identitySubtitle")}</p></div>
        <div className="form-grid">
          <label>{t("agents.new.clientLabel")}<select value={clientId} onChange={(e) => setClientId(e.target.value)}>{clients.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></label>
          <label>{t("agents.new.nameLabel")}<input value={name} onChange={(e) => setName(e.target.value)} required autoFocus placeholder={t("agents.new.namePlaceholder")} /></label>
        </div>
        {name.trim() && <p className="greeting-preview">{kind === "voice" && greeting.trim() ? greeting.trim() : t("agents.detail.greetingPreview", { name: name.trim(), client: clients.find((c) => c.id === clientId)?.name || "" })}</p>}
      </div>}

      {current === "essentials" && <div className="wizard-fields">
        <div className="wizard-copy"><h2>{t("agents.wizard.essentialsTitle")}</h2><p>{kind === "voice" ? t("phone.agent.essentialsSubtitle") : t("agents.wizard.essentialsSubtitle")}</p></div>
        <label>{t("agents.detail.briefSummaryLabel")}<textarea value={brief.summary} onChange={(e) => setBrief({ ...brief, summary: e.target.value })} rows={2} autoFocus placeholder={t("agents.detail.briefSummaryPlaceholder")} /></label>
        <label>{t("agents.detail.briefPoliciesLabel")}<textarea value={brief.policies} onChange={(e) => setBrief({ ...brief, policies: e.target.value })} rows={3} placeholder={t("agents.detail.briefPoliciesPlaceholder")} /></label>
        <label>{t("agents.new.instructionsLabel")}<textarea value={instructions} onChange={(e) => setInstructions(e.target.value)} rows={5} placeholder={kind === "voice" ? t("phone.agent.instructionsPlaceholder") : t("agents.new.instructionsPlaceholder")} /></label>
        <span className="field-help">{t("agents.wizard.essentialsLater")}</span>
      </div>}

      {current === "model" && <div className="wizard-fields">
        <div className="wizard-copy"><h2>{t("agents.wizard.modelTitle")}</h2><p>{t("agents.wizard.modelSubtitle")}</p></div>
        <label>{t("agents.new.modelLabel")}{modelPicker}</label>
        <details className="advanced-options wizard-advanced"><summary>{t("agents.detail.advancedHeading")}</summary><p className="field-help">{t("agents.detail.advancedCopy")}</p>
        {sampling}
        <label>{t("agents.detail.phoneHandoverLabel")}<input type="number" min="1" max="1440" required value={phoneHandoverMinutes} onChange={(e) => setPhoneHandoverMinutes(Number(e.target.value))} /><span className="field-help">{t("agents.detail.phoneHandoverHint")}</span></label>
        <div className="group-intro"><strong>{t("agents.detail.replyDelayHeading")}</strong></div>
        <div className="slider-field"><div className="slider-head"><span>{t("agents.detail.replyDelayMinLabel")} <AiHint text={t("agents.detail.replyDelayMinHint")} /></span><strong>{replyDelayMin}/60 s</strong></div><input type="range" min="0" max="60" step="1" value={replyDelayMin} onChange={(e) => { const v = Number(e.target.value); setReplyDelayMin(v); if (v > replyDelayMax) setReplyDelayMax(v); }} /></div>
        <div className="slider-field"><div className="slider-head"><span>{t("agents.detail.replyDelayMaxLabel")} <AiHint text={t("agents.detail.replyDelayMaxHint")} /></span><strong>{replyDelayMax}/60 s</strong></div><input type="range" min="0" max="60" step="1" value={replyDelayMax} onChange={(e) => { const v = Number(e.target.value); setReplyDelayMax(v); if (v < replyDelayMin) setReplyDelayMin(v); }} /></div>
        <div className="capabilities-intro"><strong>{t("agents.detail.capabilitiesHeading")}</strong><span className="field-help">{t("agents.detail.capabilitiesCopy")}</span></div>
        <div className="capability"><label className="capability-head"><input type="checkbox" checked={imageEnabled} onChange={(e) => setImageEnabled(e.target.checked)} /><ImageIcon size={17} /><span><strong>{t("agents.detail.imageLabel")}</strong><small>{t("agents.detail.imageHint")}</small></span></label></div>
        <div className="capability"><label className="capability-head"><input type="checkbox" checked={audioEnabled} onChange={(e) => setAudioEnabled(e.target.checked)} /><AudioLines size={17} /><span><strong>{t("agents.detail.audioLabel")}</strong><small>{t("agents.detail.audioHint")}</small></span></label></div>
        </details>
      </div>}

      {current === "review" && <div className="wizard-fields">
        <div className="wizard-copy"><h2>{t("agents.wizard.reviewTitle")}</h2><p>{kind === "voice" ? t("phone.agent.reviewSubtitle") : t("agents.wizard.reviewSubtitle")}</p></div>
        <dl className="review-list">
          <div><dt>{t("agents.new.nameLabel")}</dt><dd>{name}</dd></div>
          <div><dt>{t("agents.new.clientLabel")}</dt><dd>{clients.find((c) => c.id === clientId)?.name || ""}</dd></div>
          {kind === "voice"
            ? <><div><dt>{t("phone.agent.stepVoice")}</dt><dd>{voice.name}</dd></div><div><dt>{t("phone.agent.reviewGreeting")}</dt><dd>{greeting.trim()}</dd></div></>
            : <div><dt>{t("agents.wizard.reviewTemplate")}</dt><dd>{templateId ? localize(agentTemplates.find((x) => x.id === templateId)!.name, lang) : t("agents.wizard.blankName")}</dd></div>}
          <div><dt>{t("agents.detail.briefSummaryLabel")}</dt><dd>{brief.summary.trim() || <span className="muted">{t("agents.wizard.reviewEmpty")}</span>}</dd></div>
          {kind === "chat" && <div><dt>{t("agents.new.modelLabel")}</dt><dd>{modelOptionsFor(provider).find((item) => item.id === model)?.label || model}</dd></div>}
          <div><dt>{t("agents.wizard.reviewPrompt")}</dt><dd><span className="token-pill"><Sparkles size={13} /> {t("agents.wizard.tokens", { count: promptTokens.toLocaleString(lang) })}</span></dd></div>
        </dl>
        {kind === "voice" && <>
          <label>{t("agents.new.modelLabel")}<VoiceModelPicker value={model} onChange={setModel} /></label>
          <span className="field-help">{t("phone.agent.modelHint")}</span>
        </>}
      </div>}
    </section>

    <div className="wizard-nav">
      <button className="button secondary" onClick={() => setStep((s) => Math.max(0, s - 1))} disabled={step === 0 || busy}><ArrowLeft size={16} /> {t("agents.wizard.back")}</button>
      <span className="wizard-progress">{t("agents.wizard.stepOf", { n: step + 1, total: steps.length })}</span>
      {step < steps.length - 1
        ? <button className="button primary" onClick={() => canNext && setStep((s) => s + 1)} disabled={!canNext}>{t("agents.wizard.next")} <ArrowRight size={16} /></button>
        : <button className="button primary" onClick={create} disabled={busy || !identityDone || (kind === "voice" && !voiceDone)}>{busy ? <LoaderCircle className="spin" size={16} /> : <Check size={16} />} {t("agents.new.createAgent")}</button>}
    </div>
  </div>;
}
