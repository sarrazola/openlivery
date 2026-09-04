"use client";

// The web chat as a channel of the client, next to the WhatsApp lines: one
// per client, answered by an agent of that client. The public id in the
// snippet belongs to the channel, so swapping the agent never breaks a site.

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { ArrowLeft, Bot, Code, Copy, ExternalLink, Globe2, LoaderCircle, Palette, Save, ShieldCheck } from "lucide-react";
import { Alert } from "@/components/ui";
import { useToast } from "@/components/toast";
import { api, ApiError, messageFrom } from "@/lib/api";
import { useT } from "@/lib/i18n";
import type { Client, WidgetChannel } from "@/types";

export default function WebChatChannelPage() {
  const t = useT();
  const toast = useToast();
  const { id } = useParams<{ id: string }>();
  const [client, setClient] = useState<Client | null>(null);
  const [channel, setChannel] = useState<WidgetChannel | null>(null);
  const [agentId, setAgentId] = useState("");
  const [enabled, setEnabled] = useState(true);
  const [greeting, setGreeting] = useState("");
  const [color, setColor] = useState("#075985");
  const [position, setPosition] = useState<"right" | "left">("right");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const loadChannel = api<WidgetChannel>(`/webchat/channels/${id}`)
      .then((current) => {
        setChannel(current);
        setAgentId(current.agent_id);
        setEnabled(current.is_enabled);
        setGreeting(current.greeting);
        setColor(current.color || "#075985");
        setPosition(current.position);
      })
      .catch((err) => {
        if (!(err instanceof ApiError && err.status === 404)) throw err;
        setChannel(null);
      });
    Promise.all([
      api<Client>(`/clients/${id}`).then((item) => { setClient(item); setAgentId((value) => value || item.agents[0]?.id || ""); }),
      loadChannel,
    ]).catch((err) => setError(messageFrom(err))).finally(() => setLoading(false));
  }, [id]);

  async function save() {
    if (!agentId) return;
    setBusy(true); setError("");
    try {
      setChannel(await api<WidgetChannel>(`/webchat/channels/${id}`, { method: "PUT", body: JSON.stringify({ agent_id: agentId, is_enabled: enabled, greeting, color, position }) }));
      toast.success(t("clients.webchat.saved"));
    } catch (err) { setError(messageFrom(err)); } finally { setBusy(false); }
  }

  if (loading || !client) return <div className="page-loading"><LoaderCircle className="spin" /> {t("clients.webchat.loading")}</div>;
  const origin = typeof window === "undefined" ? "" : window.location.origin;
  const snippet = channel ? `<script src="${origin}/widget.js" data-agent="${channel.public_id}" data-color="${color}" data-position="${position}" async></script>` : "";
  const live = Boolean(channel && channel.is_enabled);
  return <div className="page wa-page">
    <Link href={`/clients/${client.id}`} className="back-link"><ArrowLeft size={17} /> {t("clients.whatsapp.back", { name: client.name })}</Link>
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
          <label>{t("clients.webchat.greeting")}<textarea rows={2} value={greeting} onChange={(event) => setGreeting(event.target.value)} placeholder={t("clients.webchat.greetingPlaceholder")} disabled={busy} /></label>
          <div className="form-grid">
            <label>{t("clients.webchat.color")}<div className="color-input"><input type="color" value={color} onChange={(event) => setColor(event.target.value)} disabled={busy} /><input value={color} onChange={(event) => setColor(event.target.value)} disabled={busy} /></div></label>
            <label>{t("clients.webchat.position")}<select value={position} onChange={(event) => setPosition(event.target.value === "left" ? "left" : "right")} disabled={busy}><option value="right">{t("clients.webchat.positionRight")}</option><option value="left">{t("clients.webchat.positionLeft")}</option></select></label>
          </div>
        </div>
        <div className="wa-actions"><button className="button primary" onClick={save} disabled={!agentId || busy}>{busy ? <LoaderCircle className="spin" size={17} /> : <Save size={17} />} {t("clients.webchat.save")}</button></div>
      </section>
      <section className="wa-panel"><div className="wa-panel-head"><span><Code size={19} /></span><div><h2>{t("clients.webchat.embedTitle")}</h2><p>{t("clients.webchat.embedCopy")}</p></div></div>
        {channel ? <>
          {!live && <Alert type="info">{t("clients.webchat.embedOff")}</Alert>}
          <pre className="embed-snippet">{snippet}</pre>
          <div className="embed-actions"><button type="button" className="button secondary" onClick={() => { navigator.clipboard.writeText(snippet); toast.success(t("clients.webchat.copied")); }}><Copy size={15} /> {t("clients.webchat.copyCode")}</button><a className="button ghost" href={`/widget/${channel.public_id}`} target="_blank" rel="noreferrer"><ExternalLink size={15} /> {t("clients.webchat.preview")}</a></div>
        </> : <Alert type="info">{t("clients.webchat.saveFirst")}</Alert>}
      </section>
    </main><aside className="wa-side"><ShieldCheck size={22} /><h3>{t("clients.webchat.sideTitle")}</h3><p>{t("clients.webchat.sideCopy")}</p><hr /><h3>{t("clients.whatsapp.humanControlTitle")}</h3><p>{t("clients.whatsapp.humanControlCopy")}</p></aside></div>
  </div>;
}
