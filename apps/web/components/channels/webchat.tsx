"use client";

// The web chat as a channel of the client, next to the WhatsApp lines: one
// per client, answered by an agent of that client. The public id in the
// snippet belongs to the channel, so swapping the agent never breaks a site.

import { useEffect, useState } from "react";
import { ArrowLeft, Bot, Code, Copy, ExternalLink, Globe2, LoaderCircle, MessageCircle, Palette, Plus, Save, ShieldCheck, Trash2 } from "lucide-react";
import { Alert } from "@/components/ui";
import { useToast } from "@/components/toast";
import { api, ApiError, messageFrom } from "@/lib/api";
import type { ChannelSetupProps } from "@/lib/channels";
import { useT } from "@/lib/i18n";
import type { WidgetAppearance, WidgetChannel } from "@/types";

const DEFAULT_LOOK: WidgetAppearance = { display: "bubble", header_title: "", header_subtitle: "", headline: "", suggestions: [], placeholder: "", footer_note: "", header_style: "solid", headline_font: "sans", corners: "round", background: "" };
const MAX_SUGGESTIONS = 6;
const HEX_COLOR = /^#[0-9a-f]{6}$/i;

export function WebChatSetup({ client, onBack }: ChannelSetupProps) {
  const t = useT();
  const toast = useToast();
  const id = client.id;
  const [channel, setChannel] = useState<WidgetChannel | null>(null);
  const [agentId, setAgentId] = useState(client.agents[0]?.id || "");
  const [enabled, setEnabled] = useState(true);
  const [greeting, setGreeting] = useState("");
  const [color, setColor] = useState("#075985");
  const [position, setPosition] = useState<"right" | "left">("right");
  const [look, setLook] = useState<WidgetAppearance>(DEFAULT_LOOK);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    api<WidgetChannel>(`/webchat/channels/${id}`)
      .then((current) => {
        setChannel(current);
        setAgentId(current.agent_id);
        setEnabled(current.is_enabled);
        setGreeting(current.greeting);
        setColor(current.color || "#075985");
        setPosition(current.position);
        setLook(current.appearance);
      })
      .catch((err) => {
        if (!(err instanceof ApiError && err.status === 404)) { setError(messageFrom(err)); return; }
        setChannel(null);
      })
      .finally(() => setLoading(false));
  }, [id]);

  async function save() {
    if (!agentId) return;
    setBusy(true); setError("");
    try {
      const saved = await api<WidgetChannel>(`/webchat/channels/${id}`, { method: "PUT", body: JSON.stringify({ agent_id: agentId, is_enabled: enabled, greeting, color, position, appearance: look }) });
      setChannel(saved);
      setLook(saved.appearance);
      toast.success(t("clients.webchat.saved"));
    } catch (err) { setError(messageFrom(err)); } finally { setBusy(false); }
  }

  if (loading) return <div className="page-loading"><LoaderCircle className="spin" /> {t("clients.webchat.loading")}</div>;
  const origin = typeof window === "undefined" ? "" : window.location.origin;
  const inline = look.display === "inline";
  const script = channel ? `<script src="${origin}/widget.js" data-agent="${channel.public_id}"` : "";
  const snippet = !channel ? "" : inline
    ? `<div id="openlivery-chat"></div>\n${script} data-mode="inline" data-target="#openlivery-chat" async></script>`
    : `${script} data-color="${color}" data-position="${position}" async></script>`;
  const live = Boolean(channel && channel.is_enabled);
  const patchLook = (patch: Partial<WidgetAppearance>) => setLook((current) => ({ ...current, ...patch }));
  const setSuggestion = (index: number, value: string) => patchLook({ suggestions: look.suggestions.map((item, at) => (at === index ? value : item)) });
  const backgroundValid = !look.background || HEX_COLOR.test(look.background);
  const agentName = client.agents.find((agent) => agent.id === agentId)?.name;
  const cornersField = <label>{t("clients.webchat.corners")}<select value={look.corners} onChange={(event) => patchLook({ corners: event.target.value as WidgetAppearance["corners"] })} disabled={busy}><option value="round">{t("clients.webchat.cornersRound")}</option><option value="soft">{t("clients.webchat.cornersSoft")}</option><option value="square">{t("clients.webchat.cornersSquare")}</option></select></label>;
  return <div className="wa-page">
    <button type="button" className="back-link" onClick={onBack}><ArrowLeft size={17} /> {t("clients.detail.channelsBack")}</button>
    <header className="wa-header"><div className="wa-mark"><Globe2 size={26} /></div><div><span>{t("clients.whatsapp.channelOf", { name: client.name })}</span><h1>{t("clients.webchat.title")}</h1><p>{t("clients.webchat.headerCopy")}</p></div>{channel && <span className={live ? "pill purple" : "pill"}>{live ? t("clients.webchat.live") : t("clients.webchat.off")}</span>}</header>
    {error && <Alert>{error}</Alert>}
    <div className="wa-layout"><main>
      <section className="wa-panel"><div className="wa-panel-head"><span><Bot size={19} /></span><div><h2>{t("clients.whatsapp.assignedAgent")}</h2><p>{t("clients.whatsapp.assignedAgentCopy")}</p></div></div>
        <div className="wa-agent-row"><label>{t("clients.whatsapp.agentToRespond")}<select value={agentId} onChange={(event) => setAgentId(event.target.value)} disabled={busy}><option value="">{t("clients.whatsapp.selectAgent")}</option>{client.agents.map((agent) => <option key={agent.id} value={agent.id}>{agent.name}{agent.is_active ? "" : t("clients.whatsapp.inactiveSuffix")}</option>)}</select></label></div>
        {!client.agents.length && <Alert>{t("clients.whatsapp.needsAgent")}</Alert>}
      </section>
      <section className="wa-panel"><div className="wa-panel-head"><span><Palette size={19} /></span><div><h2>{t("clients.webchat.appearanceTitle")}</h2><p>{t("clients.webchat.appearanceCopy")}</p></div></div>
        <div className="webchat-form">
          <label className="switch-row"><span><strong>{t("clients.webchat.enable")}</strong><small>{t("clients.webchat.enableHint")}</small></span><input type="checkbox" checked={enabled} onChange={(event) => setEnabled(event.target.checked)} disabled={busy} /></label>
          <div className="form-grid">
            <label>{t("clients.webchat.display")}<select value={look.display} onChange={(event) => patchLook({ display: event.target.value === "inline" ? "inline" : "bubble" })} disabled={busy}><option value="bubble">{t("clients.webchat.displayBubble")}</option><option value="inline">{t("clients.webchat.displayInline")}</option></select></label>
            {inline ? cornersField : <label>{t("clients.webchat.position")}<select value={position} onChange={(event) => setPosition(event.target.value === "left" ? "left" : "right")} disabled={busy}><option value="right">{t("clients.webchat.positionRight")}</option><option value="left">{t("clients.webchat.positionLeft")}</option></select></label>}
            <label>{t("clients.webchat.color")}<div className="color-input"><input type="color" value={color} onChange={(event) => setColor(event.target.value)} disabled={busy} /><input value={color} onChange={(event) => setColor(event.target.value)} disabled={busy} /></div></label>
            <label>{t("clients.webchat.background")}<div className="color-input"><input type="color" value={HEX_COLOR.test(look.background) ? look.background : "#ffffff"} onChange={(event) => patchLook({ background: event.target.value })} disabled={busy} /><input value={look.background} onChange={(event) => patchLook({ background: event.target.value.trim() })} placeholder={t("clients.webchat.backgroundDefault")} aria-invalid={!backgroundValid} disabled={busy} /></div></label>
            <label>{t("clients.webchat.headerStyle")}<select value={look.header_style} onChange={(event) => patchLook({ header_style: event.target.value === "plain" ? "plain" : "solid" })} disabled={busy}><option value="solid">{t("clients.webchat.headerSolid")}</option><option value="plain">{t("clients.webchat.headerPlain")}</option></select></label>
            <label>{t("clients.webchat.headlineFont")}<select value={look.headline_font} onChange={(event) => patchLook({ headline_font: event.target.value === "serif" ? "serif" : "sans" })} disabled={busy}><option value="sans">{t("clients.webchat.fontSans")}</option><option value="serif">{t("clients.webchat.fontSerif")}</option></select></label>
            {!inline && cornersField}
          </div>
        </div>
      </section>
      <section className="wa-panel"><div className="wa-panel-head"><span><MessageCircle size={19} /></span><div><h2>{t("clients.webchat.startTitle")}</h2><p>{t("clients.webchat.startCopy")}</p></div></div>
        <div className="webchat-form">
          <label>{t("clients.webchat.headline")}<input value={look.headline} maxLength={160} onChange={(event) => patchLook({ headline: event.target.value })} placeholder={t("clients.webchat.headlinePlaceholder")} disabled={busy} /></label>
          <label>{t("clients.webchat.greeting")}<textarea rows={2} value={greeting} onChange={(event) => setGreeting(event.target.value)} placeholder={t("clients.webchat.greetingPlaceholder")} disabled={busy} /></label>
          <div className="webchat-suggestions"><span>{t("clients.webchat.suggestions")}<small>{t("clients.webchat.suggestionsHint", { count: MAX_SUGGESTIONS })}</small></span>
            {look.suggestions.map((suggestion, index) => <div key={index}><input autoFocus={!suggestion} value={suggestion} maxLength={60} onChange={(event) => setSuggestion(index, event.target.value)} placeholder={t("clients.webchat.suggestionPlaceholder")} aria-label={t("clients.webchat.suggestions")} disabled={busy} /><button type="button" className="icon-button danger" onClick={() => patchLook({ suggestions: look.suggestions.filter((_, at) => at !== index) })} title={t("clients.webchat.removeSuggestion")} aria-label={t("clients.webchat.removeSuggestion")} disabled={busy}><Trash2 size={14} /></button></div>)}
            {look.suggestions.length < MAX_SUGGESTIONS && <button type="button" className="button ghost small" onClick={() => patchLook({ suggestions: [...look.suggestions, ""] })} disabled={busy}><Plus size={15} /> {t("clients.webchat.addSuggestion")}</button>}
          </div>
          <div className="form-grid">
            <label>{t("clients.webchat.headerTitle")}<input value={look.header_title} maxLength={80} onChange={(event) => patchLook({ header_title: event.target.value })} placeholder={agentName} disabled={busy} /></label>
            <label>{t("clients.webchat.headerSubtitle")}<input value={look.header_subtitle} maxLength={120} onChange={(event) => patchLook({ header_subtitle: event.target.value })} placeholder={t("clients.webchat.headerSubtitleDefault")} disabled={busy} /></label>
            <label>{t("clients.webchat.placeholder")}<input value={look.placeholder} maxLength={120} onChange={(event) => patchLook({ placeholder: event.target.value })} placeholder={t("playground.composer.placeholder")} disabled={busy} /></label>
            <label>{t("clients.webchat.footerNote")}<input value={look.footer_note} maxLength={160} onChange={(event) => patchLook({ footer_note: event.target.value })} disabled={busy} /></label>
          </div>
        </div>
        <div className="wa-actions"><button className="button primary" onClick={save} disabled={!agentId || busy || !backgroundValid}>{busy ? <LoaderCircle className="spin" size={17} /> : <Save size={17} />} {t("clients.webchat.save")}</button></div>
      </section>
      <section className="wa-panel"><div className="wa-panel-head"><span><Code size={19} /></span><div><h2>{t("clients.webchat.embedTitle")}</h2><p>{t(inline ? "clients.webchat.embedCopyInline" : "clients.webchat.embedCopy")}</p></div></div>
        {channel ? <>
          {!live && <Alert type="info">{t("clients.webchat.embedOff")}</Alert>}
          <pre className="embed-snippet">{snippet}</pre>
          <div className="embed-actions"><button type="button" className="button secondary" onClick={() => { navigator.clipboard.writeText(snippet); toast.success(t("clients.webchat.copied")); }}><Copy size={15} /> {t("clients.webchat.copyCode")}</button><a className="button ghost" href={`/widget/${channel.public_id}${inline ? "?mode=inline" : ""}`} target="_blank" rel="noreferrer"><ExternalLink size={15} /> {t("clients.webchat.preview")}</a></div>
        </> : <Alert type="info">{t("clients.webchat.saveFirst")}</Alert>}
      </section>
    </main><aside className="wa-side"><ShieldCheck size={22} /><h3>{t("clients.webchat.sideTitle")}</h3><p>{t("clients.webchat.sideCopy")}</p><hr /><h3>{t("clients.whatsapp.humanControlTitle")}</h3><p>{t("clients.whatsapp.humanControlCopy")}</p></aside></div>
  </div>;
}
