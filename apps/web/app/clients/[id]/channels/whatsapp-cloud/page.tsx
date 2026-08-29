"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { ArrowLeft, BadgeCheck, Bot, CheckCircle2, CircleAlert, ClipboardCopy, KeyRound, LoaderCircle, Plug, Power, RefreshCw, ShieldCheck, Smartphone, Webhook } from "lucide-react";
import { Alert } from "@/components/ui";
import { api, ApiError, messageFrom } from "@/lib/api";
import { useT, type I18nKey } from "@/lib/i18n";
import type { Client, WhatsAppCloudChannel } from "@/types";

const stateKeys: Record<WhatsAppCloudChannel["status"], { label: I18nKey; copy: I18nKey }> = {
  disconnected: { label: "clients.whatsappCloud.statusDisconnectedLabel", copy: "clients.whatsappCloud.statusDisconnectedCopy" },
  connected: { label: "clients.whatsappCloud.statusConnectedLabel", copy: "clients.whatsappCloud.statusConnectedCopy" },
  error: { label: "clients.whatsappCloud.statusErrorLabel", copy: "clients.whatsappCloud.statusErrorCopy" },
};

function CopyField({ label, value }: { label: string; value: string }) {
  const t = useT();
  const [copied, setCopied] = useState(false);
  async function copy() {
    await navigator.clipboard.writeText(value);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1600);
  }
  return <div className="wa-copy-field">
    <label>{label}<input readOnly value={value} onFocus={(event) => event.currentTarget.select()} /></label>
    <button type="button" className="button secondary" onClick={copy}><ClipboardCopy size={15} /> {copied ? t("clients.whatsappCloud.copied") : t("clients.whatsappCloud.copy")}</button>
  </div>;
}

export default function WhatsAppCloudChannelPage() {
  const t = useT();
  const { id } = useParams<{ id: string }>();
  const [client, setClient] = useState<Client | null>(null);
  const [channel, setChannel] = useState<WhatsAppCloudChannel | null>(null);
  const [agentId, setAgentId] = useState("");
  const [phoneNumberId, setPhoneNumberId] = useState("");
  const [wabaId, setWabaId] = useState("");
  const [accessToken, setAccessToken] = useState("");
  const [appSecret, setAppSecret] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const loadChannel = api<WhatsAppCloudChannel>(`/whatsapp-cloud/channels/${id}`)
      .then((current) => {
        setChannel(current);
        setAgentId(current.agent_id);
        setPhoneNumberId(current.phone_number_id);
        setWabaId(current.waba_id || "");
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

  async function save(): Promise<WhatsAppCloudChannel | null> {
    if (!agentId) return null;
    const payload: Record<string, string> = { agent_id: agentId, phone_number_id: phoneNumberId.trim(), waba_id: wabaId.trim() };
    if (accessToken.trim()) payload.access_token = accessToken.trim();
    if (appSecret.trim()) payload.app_secret = appSecret.trim();
    const saved = await api<WhatsAppCloudChannel>(`/whatsapp-cloud/channels/${id}`, { method: "PUT", body: JSON.stringify(payload) });
    setChannel(saved);
    setAccessToken("");
    setAppSecret("");
    return saved;
  }

  async function saveOnly() {
    setBusy(true); setError("");
    try { await save(); } catch (err) { setError(messageFrom(err)); } finally { setBusy(false); }
  }

  async function saveAndConnect() {
    setBusy(true); setError("");
    try {
      if (await save()) setChannel(await api<WhatsAppCloudChannel>(`/whatsapp-cloud/channels/${id}/connect`, { method: "POST" }));
    } catch (err) { setError(messageFrom(err)); } finally { setBusy(false); }
  }

  async function disconnect() {
    if (!confirm(t("clients.whatsappCloud.confirmDisconnect"))) return;
    setBusy(true); setError("");
    try { setChannel(await api<WhatsAppCloudChannel>(`/whatsapp-cloud/channels/${id}/disconnect`, { method: "POST" })); }
    catch (err) { setError(messageFrom(err)); } finally { setBusy(false); }
  }

  if (loading || !client) return <div className="page-loading"><LoaderCircle className="spin" /> {t("clients.whatsappCloud.loading")}</div>;
  const state = stateKeys[channel?.status || "disconnected"];
  const canConnect = Boolean(agentId && phoneNumberId.trim() && !busy);
  return <div className="page wa-page">
    <Link href={`/clients/${client.id}`} className="back-link"><ArrowLeft size={17} /> {t("clients.whatsapp.back", { name: client.name })}</Link>
    <header className="wa-header"><div className="wa-mark"><BadgeCheck size={26} /></div><div><span>{t("clients.whatsapp.channelOf", { name: client.name })}</span><h1>{t("clients.whatsappCloud.title")}</h1><p>{t("clients.whatsappCloud.headerCopy")}</p></div>{channel && <div className={`wa-state ${channel.status}`}>{channel.status === "connected" ? <CheckCircle2 size={17} /> : channel.status === "error" ? <CircleAlert size={17} /> : <RefreshCw size={17} />} {t(state.label)}</div>}</header>
    {error && <Alert>{error}</Alert>}
    <div className="wa-layout"><main>
      <section className="wa-panel"><div className="wa-panel-head"><span><Bot size={19} /></span><div><h2>{t("clients.whatsapp.assignedAgent")}</h2><p>{t("clients.whatsapp.assignedAgentCopy")}</p></div></div><div className="wa-agent-row"><label>{t("clients.whatsapp.agentToRespond")}<select value={agentId} onChange={(event) => setAgentId(event.target.value)} disabled={busy}><option value="">{t("clients.whatsapp.selectAgent")}</option>{client.agents.map((agent) => <option key={agent.id} value={agent.id}>{agent.name}{agent.is_active ? "" : t("clients.whatsapp.inactiveSuffix")}</option>)}</select></label></div>{!client.agents.length && <Alert>{t("clients.whatsapp.needsAgent")}</Alert>}</section>
      <section className="wa-panel"><div className="wa-panel-head"><span><KeyRound size={19} /></span><div><h2>{t("clients.whatsappCloud.credentialsTitle")}</h2><p>{t("clients.whatsappCloud.credentialsCopy")} <a href={t("clients.whatsappCloud.guideUrl")} target="_blank" rel="noreferrer">{t("clients.whatsappCloud.guideLink")}</a>.</p></div></div>
        <div className="wa-cloud-form">
          <label>{t("clients.whatsappCloud.phoneNumberIdLabel")}<input value={phoneNumberId} onChange={(event) => setPhoneNumberId(event.target.value)} disabled={busy} /></label>
          <label>{t("clients.whatsappCloud.wabaIdLabel")}<input value={wabaId} onChange={(event) => setWabaId(event.target.value)} disabled={busy} /></label>
          <label>{t("clients.whatsappCloud.accessTokenLabel")}<input type="password" value={accessToken} onChange={(event) => setAccessToken(event.target.value)} placeholder={channel?.has_access_token ? t("clients.whatsappCloud.secretSavedPlaceholder") : ""} disabled={busy} /></label>
          <label>{t("clients.whatsappCloud.appSecretLabel")}<input type="password" value={appSecret} onChange={(event) => setAppSecret(event.target.value)} placeholder={channel?.has_app_secret ? t("clients.whatsappCloud.secretSavedPlaceholder") : ""} disabled={busy} /></label>
        </div>
        {channel?.status === "connected" && <div className="wa-connected"><div className="wa-phone"><Smartphone size={24} /><span><small>{t("clients.whatsapp.connectedNumber")}</small><strong>{channel.phone_number || channel.phone_number_id}</strong>{channel.display_name && <em>{channel.display_name}</em>}</span></div><div className="wa-ready"><CheckCircle2 size={18} /> {t("clients.whatsapp.readyForMessages")}</div></div>}
        {channel?.last_error && <Alert>{channel.last_error}</Alert>}
        <div className="wa-actions">
          <button className="button secondary" onClick={saveOnly} disabled={!agentId || busy}>{t("clients.whatsappCloud.save")}</button>
          <button className="button primary" onClick={saveAndConnect} disabled={!canConnect}>{busy ? <LoaderCircle className="spin" size={17} /> : <Plug size={17} />} {t("clients.whatsappCloud.connectVerify")}</button>
          {channel?.status === "connected" && <button className="button danger" onClick={disconnect} disabled={busy}><Power size={17} /> {t("clients.whatsappCloud.disconnect")}</button>}
        </div>
      </section>
      {channel && <section className="wa-panel"><div className="wa-panel-head"><span><Webhook size={19} /></span><div><h2>{t("clients.whatsappCloud.webhookTitle")}</h2><p>{t("clients.whatsappCloud.webhookCopy")}</p></div></div>
        <CopyField label={t("clients.whatsappCloud.webhookUrlLabel")} value={channel.webhook_url} />
        <CopyField label={t("clients.whatsappCloud.verifyTokenLabel")} value={channel.webhook_verify_token} />
        <ol className="wa-webhook-steps"><li>{t("clients.whatsappCloud.webhookStep1")}</li><li>{t("clients.whatsappCloud.webhookStep2")}</li><li>{t("clients.whatsappCloud.webhookStep3")}</li></ol>
      </section>}
    </main><aside className="wa-side"><ShieldCheck size={22} /><h3>{t("clients.whatsapp.separationTitle")}</h3><p>{t("clients.whatsapp.separationCopy")}<strong>{client.name}</strong>.</p><hr /><h3>{t("clients.whatsapp.humanControlTitle")}</h3><p>{t("clients.whatsapp.humanControlCopy")}</p></aside></div>
  </div>;
}
