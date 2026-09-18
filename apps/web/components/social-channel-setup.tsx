"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { ArrowLeft, Bot, CheckCircle2, ChevronDown, CircleAlert, Facebook, Instagram, History, KeyRound, LoaderCircle, Plug, Power, ShieldCheck, Webhook } from "lucide-react";
import { Alert, Modal } from "@/components/ui";
import { LineSwitcher, type LineState } from "@/components/line-switcher";
import { api, ApiError, messageFrom } from "@/lib/api";
import { accountName } from "@/lib/channels";
import { useLanguage } from "@/lib/i18n";
import type { Client, SocialChannel, SocialConfig, SocialHistoryJob, SocialPending, SocialProvider } from "@/types";

const lineState = (line: SocialChannel): LineState => (line.is_enabled && line.status === "connected" ? "connected" : "disconnected");

/** A client's accounts on one provider. One is selected at a time and the
 * panels below configure that one; "connect another account" starts a new
 * one, through the same authorization or manual credentials. */
export function SocialChannelSetup({ provider }: { provider: SocialProvider }) {
  const { t, lang } = useLanguage();
  const { id } = useParams<{ id: string }>();
  const [client, setClient] = useState<Client | null>(null);
  const [config, setConfig] = useState<SocialConfig[SocialProvider] | null>(null);
  const [lines, setLines] = useState<SocialChannel[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [pending, setPending] = useState<SocialPending | null>(null);
  const [disconnectOpen, setDisconnectOpen] = useState(false);
  const [accountChoice, setAccountChoice] = useState("");
  const [agentId, setAgentId] = useState("");
  const [label, setLabel] = useState("");
  const [accountId, setAccountId] = useState("");
  const [appId, setAppId] = useState("");
  const [accessToken, setAccessToken] = useState("");
  const [appSecret, setAppSecret] = useState("");
  const [humanAgent, setHumanAgent] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [callbackIssue, setCallbackIssue] = useState<"failed" | "expired" | "empty" | null>(null);
  const [saved, setSaved] = useState(false);
  const [historyJob, setHistoryJob] = useState<SocialHistoryJob | null>(null);
  const [historyPollFailed, setHistoryPollFailed] = useState(false);
  const channel = adding ? null : lines.find((line) => line.id === selectedId) ?? null;
  // The selected account's routes; with none selected, the client's, which adds one.
  const path = `/social/${provider}/channels/${channel?.id ?? id}`;
  const Icon = provider === "instagram" ? Instagram : Facebook;
  const guideUrl = provider === "instagram"
    ? "https://developers.facebook.com/documentation/instagram-platform/instagram-api-with-instagram-login"
    : "https://developers.facebook.com/documentation/business-messaging/messenger-platform/get-started";

  const upsert = useCallback((current: SocialChannel) => {
    setLines((items) => items.some((item) => item.id === current.id) ? items.map((item) => (item.id === current.id ? current : item)) : [...items, current]);
  }, []);

  const applyChannel = useCallback((current: SocialChannel) => {
    upsert(current);
    setAdding(false);
    setSelectedId(current.id);
    setAgentId(current.agent_id);
    setLabel(current.label || "");
    setAccountId(current.external_account_id || "");
    setAppId(current.app_id || "");
    setHumanAgent(current.human_agent_enabled);
    setAccessToken("");
    setAppSecret("");
  }, [upsert]);

  const startAdding = useCallback((owner: Client | null) => {
    setAdding(true); setSelectedId(null);
    setAgentId(owner?.agents[0]?.id || ""); setLabel(""); setAccountId(""); setAppId(""); setHumanAgent(false);
    setAccessToken(""); setAppSecret(""); setError(""); setSaved(false);
  }, []);

  const loadHistory = useCallback(async (channelId: string) => {
    try {
      setHistoryJob(await api<SocialHistoryJob>(`/social/${provider}/channels/${channelId}/import-history`));
      setHistoryPollFailed(false);
    } catch (err) {
      setHistoryJob(null);
      if (!(err instanceof ApiError && err.status === 404)) setHistoryPollFailed(true);
    }
  }, [provider]);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const [owner, setup, items, selection] = await Promise.all([
        api<Client>(`/clients/${id}`),
        api<SocialConfig>("/social/config"),
        api<SocialChannel[]>(`/social/${provider}/clients/${id}/channels`),
        api<SocialPending>(`/social/${provider}/oauth/pending?client_id=${encodeURIComponent(id)}`).catch((err) => {
          if (err instanceof ApiError && err.status === 404) return null;
          throw err;
        }),
      ]);
      setClient(owner); setConfig(setup[provider]); setLines(items); setPending(selection);
      if (items[0]) { applyChannel(items[0]); await loadHistory(items[0].id); }
      else startAdding(owner);
      setAccountChoice(selection?.accounts.length === 1 ? selection.accounts[0].id : "");
      const callbackStatus = new URLSearchParams(window.location.search).get("social_status");
      if (callbackStatus === "error") setCallbackIssue("failed");
      if (callbackStatus === "ready" && !selection) setCallbackIssue("expired");
      if (selection && !selection.accounts.length) setCallbackIssue("empty");
      if (callbackStatus) {
        const clean = new URL(window.location.href);
        clean.searchParams.delete("social_status");
        window.history.replaceState(window.history.state, "", clean.pathname + clean.search + clean.hash);
      }
    } catch (err) { setError(messageFrom(err)); }
    finally { setLoading(false); }
  }, [id, provider, applyChannel, startAdding, loadHistory]);
  useEffect(() => { void load(); }, [load]);
  const importing = historyJob?.status === "pending" || historyJob?.status === "processing";
  const channelId = channel?.id ?? null;
  useEffect(() => {
    if (!importing || !channelId) return;
    let cancelled = false;
    let polling = false;
    const timer = window.setInterval(async () => {
      if (polling) return;
      polling = true;
      try {
        const job = await api<SocialHistoryJob>(`/social/${provider}/channels/${channelId}/import-history`);
        if (!cancelled) { setHistoryJob(job); setHistoryPollFailed(false); }
      } catch {
        if (!cancelled) setHistoryPollFailed(true);
      } finally { polling = false; }
    }, 3000);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [provider, channelId, importing]);

  async function run(action: () => Promise<void>) {
    setBusy(true); setError(""); setCallbackIssue(null); setSaved(false);
    try { await action(); }
    catch (err) { setError(messageFrom(err)); }
    finally { setBusy(false); }
  }

  function select(lineId: string) {
    const line = lines.find((item) => item.id === lineId);
    if (!line) return;
    applyChannel(line); setError(""); setSaved(false);
    void loadHistory(line.id);
  }

  async function authorize() {
    await run(async () => {
      const result = await api<{ authorization_url: string }>(`/social/${provider}/oauth/start`, {
        method: "POST", body: JSON.stringify({ client_id: id, agent_id: agentId, next_path: `/clients/${id}/channels/${provider}` }),
      });
      const url = new URL(result.authorization_url);
      const allowedHost = provider === "instagram" ? "www.instagram.com" : "www.facebook.com";
      if (url.protocol !== "https:" || (url.hostname !== allowedHost && url.hostname !== allowedHost.replace("www.", ""))) throw new Error(t("social.authorizationFailed"));
      window.location.assign(url.href);
    });
  }

  async function complete() {
    if (!pending || !accountChoice) return;
    await run(async () => {
      const connected = await api<SocialChannel>(`/social/${provider}/oauth/complete`, {
        method: "POST", body: JSON.stringify({ setup_id: pending.setup_id, external_account_id: accountChoice }),
      });
      applyChannel(connected); setPending(null); setSaved(true);
      await loadHistory(connected.id);
    });
  }

  async function saveDetails() {
    if (!channel) return;
    await run(async () => {
      applyChannel(await api<SocialChannel>(path, { method: "PATCH", body: JSON.stringify({ agent_id: agentId, label: label.trim() }) }));
      setSaved(true);
    });
  }

  async function saveManual() {
    await run(async () => {
      const payload: Record<string, string | boolean> = { agent_id: agentId, label: label.trim(), external_account_id: accountId.trim(), human_agent_enabled: humanAgent };
      if (appId.trim()) payload.app_id = appId.trim();
      if (accessToken.trim()) payload.access_token = accessToken.trim();
      if (appSecret.trim()) payload.app_secret = appSecret.trim();
      applyChannel(await api<SocialChannel>(path, { method: "PUT", body: JSON.stringify(payload) }));
      setSaved(true);
    });
  }

  async function importHistory() {
    if (importing || !channel) return;
    await run(async () => {
      setHistoryJob(await api<SocialHistoryJob>(`${path}/import-history`, { method: "POST", body: "{}" }));
      setHistoryPollFailed(false);
    });
  }

  async function disconnect() {
    if (!channel) return;
    await run(async () => {
      await api(`${path}/disconnect`, { method: "POST" });
      // The account is gone; the page shows the next one, or starts over.
      const rest = lines.filter((line) => line.id !== channel.id);
      setLines(rest); setDisconnectOpen(false); setPending(null); setHistoryJob(null);
      if (rest[0]) { applyChannel(rest[0]); void loadHistory(rest[0].id); } else startAdding(client);
    });
  }

  if (loading) return <div className="page-loading"><LoaderCircle className="spin" /> {t("social.loading")}</div>;
  if (!client || !config) return <div className="page"><Alert>{error || t("social.loadFailed")}</Alert><button className="button secondary" onClick={load}>{t("social.retry")}</button></div>;
  const connected = channel?.status === "connected" && channel.is_enabled;
  const statusLabel = connected ? "social.connected" : channel?.status === "error" ? "social.error" : channel?.status === "expired" ? "social.expired" : "social.disconnected";
  const manualAvailable = config.source === "operator" && config.manual_available;
  const canSaveManual = agentId && accountId.trim() && (accessToken.trim() || channel?.has_access_token) && !busy;
  const dirty = Boolean(channel && (channel.agent_id !== agentId || (channel.label || "") !== label.trim()));
  const nameOf = (line: SocialChannel) => accountName(line, t("social.accountFallback", { n: lines.indexOf(line) + 1 }));

  return <div className="page wa-page social-page">
    <Link href={`/clients/${id}`} className="back-link"><ArrowLeft size={17} /> {t("clients.whatsapp.back", { name: client.name })}</Link>
    <header className="wa-header"><div className={`wa-mark ${provider}`}><Icon size={26} /></div><div><span>{t("clients.whatsapp.channelOf", { name: client.name })}</span><h1>{t(`social.${provider}.title`)}</h1><p>{t(`social.${provider}.description`)}</p></div>{channel && <div className={`wa-state ${connected ? "connected" : channel.status === "error" ? "error" : "disconnected"}`}>{connected ? <CheckCircle2 size={17} /> : <CircleAlert size={17} />} {t(statusLabel)}</div>}</header>
    <LineSwitcher lines={lines.map((line) => ({ id: line.id, name: nameOf(line), state: lineState(line) }))} selectedId={selectedId} adding={adding} addLabel={t("social.addAccount")} newLabel={t("social.newAccount")} onSelect={select} onAdd={() => startAdding(client)} />
    {error && <Alert>{error}</Alert>}
    {callbackIssue && <Alert>{t(callbackIssue === "failed" ? "social.authorizationFailed" : callbackIssue === "expired" ? "social.authorizationExpired" : "social.authorizationEmpty")}</Alert>}
    {saved && <p className="social-feedback" role="status"><CheckCircle2 size={16} /> {t("social.saved")}</p>}
    <div className="wa-layout"><main>
      <section className="wa-panel"><div className="wa-panel-head"><span><Bot size={19} /></span><div><h2>{t("clients.whatsapp.assignedAgent")}</h2><p>{t("clients.whatsapp.assignedAgentCopy")}</p></div></div><div className="wa-agent-row"><label>{t("clients.whatsapp.agentToRespond")}<select value={agentId} onChange={(event) => setAgentId(event.target.value)} disabled={busy || Boolean(pending)}><option value="">{t("clients.whatsapp.selectAgent")}</option>{client.agents.map((agent) => <option key={agent.id} value={agent.id}>{agent.name}{agent.is_active ? "" : t("clients.whatsapp.inactiveSuffix")}</option>)}</select></label><label>{t("social.accountName")}<input value={label} maxLength={80} placeholder={t("social.accountNamePlaceholder")} onChange={(event) => setLabel(event.target.value)} disabled={busy || Boolean(pending)} /></label>{channel && <button className="button secondary" disabled={!agentId || !dirty || busy || Boolean(pending)} onClick={saveDetails}>{t("social.agentSave")}</button>}</div><p className="social-meta">{t("social.accountNameHint")}</p>{!client.agents.length && <Alert>{t("clients.whatsapp.needsAgent")}</Alert>}</section>
      <section className="wa-panel"><div className="wa-panel-head"><span><Plug size={19} /></span><div><h2>{t("social.accountTitle")}</h2><p>{t("social.accountCopy")}</p></div></div>
        <p>{t(`social.${provider}.requirement`)}</p>
        {channel && <div className="social-account"><Icon size={24} /><div><strong>{channel.display_name || channel.username || channel.external_account_id}</strong>{channel.username && <small>@{channel.username.replace(/^@/, "")}</small>}<small>{channel.external_account_id}</small>{connected && <small>{t("social.connectedCopy")}</small>}</div></div>}
        {channel?.last_error && <Alert>{channel.last_error}</Alert>}
        {pending && <div className="social-selection"><h3>{t("social.chooseAccount")}</h3><p>{t("social.chooseAccountCopy")}</p><label>{t("social.chooseAccount")}<select value={accountChoice} onChange={(event) => setAccountChoice(event.target.value)} disabled={busy}><option value="">{t("social.accountPlaceholder")}</option>{pending.accounts.map((account) => <option key={account.id} value={account.id}>{account.name}{account.username ? ` (@${account.username})` : ""} · {account.id}</option>)}</select></label><button className="button primary" onClick={complete} disabled={!accountChoice || busy}>{busy ? <LoaderCircle className="spin" size={17} /> : <CheckCircle2 size={17} />} {t("social.finish")}</button></div>}
        {!config.oauth_ready && <p className="social-setup-notice">{t(config.source === "managed" ? "social.managedNotReady" : "social.operatorNotReady")}</p>}
        <div className="wa-actions"><button className="button primary" onClick={authorize} disabled={!config.oauth_ready || !agentId || busy}>{busy ? <LoaderCircle className="spin" size={17} /> : <Plug size={17} />} {t(channel || pending ? "social.reconnect" : "social.connect")}</button>{channel?.has_access_token && <button className="button secondary" disabled={busy} onClick={() => run(async () => { applyChannel(await api<SocialChannel>(`${path}/connect`, { method: "POST" })); setSaved(true); })}>{t(connected ? "social.verify" : "social.connectSaved")}</button>}{channel && <button className="button danger" onClick={() => setDisconnectOpen(true)} disabled={busy}><Power size={17} /> {t("social.disconnect")}</button>}</div>
        <Modal open={disconnectOpen} title={t("social.disconnectTitle", { name: channel?.display_name || channel?.username || channel?.external_account_id || "" })} onClose={() => setDisconnectOpen(false)}>
          <div className="modal-form">
            <p className="modal-copy">{t("social.disconnectCopy")}</p>
            <div className="modal-actions"><button type="button" className="button" onClick={() => setDisconnectOpen(false)}>{t("common.cancel")}</button><button type="button" className="button danger" disabled={busy} onClick={disconnect}>{busy ? <LoaderCircle className="spin" size={16} /> : <><Power size={15} /> {t("social.disconnect")}</>}</button></div>
          </div>
        </Modal>
        {channel?.token_expires_at && <p className="social-meta">{t("social.tokenExpires")}: {new Date(channel.token_expires_at).toLocaleString(lang)}</p>}
        {channel?.granted_scopes?.length ? <details className="social-permissions"><summary>{t("social.permissions")}</summary><ul>{channel.granted_scopes.map((scope) => <li key={scope}><code>{scope}</code></li>)}</ul></details> : null}
      </section>
      {channel && (connected || historyJob) && <section className="wa-panel"><div className="wa-panel-head"><span><History size={19} /></span><div><h2>{t("social.historyTitle")}</h2><p>{t("social.importHistoryCopy")}</p></div></div>{provider === "instagram" && <p className="social-meta">{t("social.instagramHistoryLimit")}</p>}{historyJob && <div className="social-history-status" role="status"><strong>{t(historyJob.status === "pending" ? "social.historyPending" : historyJob.status === "processing" ? "social.historyProcessing" : historyJob.status === "completed" ? "social.historyCompleted" : "social.historyFailed")}</strong><small>{t("social.historyCounts", { conversations: historyJob.conversations_count, messages: historyJob.messages_count })}</small></div>}{historyJob?.last_error && <Alert>{historyJob.last_error}</Alert>}{historyPollFailed && <p className="social-meta" role="status">{t("social.historyPollError")}</p>}<div className="wa-actions"><button className="button secondary" onClick={importHistory} disabled={!connected || importing || busy}>{importing ? <LoaderCircle className="spin" size={17} /> : <History size={17} />} {t("social.importHistory")}</button></div></section>}
      {manualAvailable && <details className="wa-panel social-manual"><summary><KeyRound size={19} /> {t("social.manualTitle")}<ChevronDown className="social-disclosure" size={16} /></summary><p>{t("social.manualCopy")} <a href={guideUrl} target="_blank" rel="noreferrer">{t("social.guide")}</a>.</p><div className="wa-cloud-form"><label>{t(provider === "instagram" ? "social.instagramAppId" : "social.metaAppId")}<input value={appId} onChange={(event) => setAppId(event.target.value)} disabled={busy} autoComplete="off" /></label><label>{t(provider === "instagram" ? "social.accountId" : "social.pageId")}<input value={accountId} onChange={(event) => setAccountId(event.target.value)} disabled={busy} autoComplete="off" /></label><label>{t("social.accessToken")}<input type="password" value={accessToken} onChange={(event) => setAccessToken(event.target.value)} placeholder={channel?.has_access_token ? t("social.secretSaved") : ""} disabled={busy} autoComplete="new-password" /></label><label>{t("social.appSecret")}<input type="password" value={appSecret} onChange={(event) => setAppSecret(event.target.value)} placeholder={channel?.has_app_secret ? t("social.secretSaved") : ""} disabled={busy} autoComplete="new-password" /></label></div><label className="switch-row social-human-agent"><span><strong>{t("social.humanAgent")}</strong><small>{t("social.humanAgentCopy")}</small></span><input type="checkbox" checked={humanAgent} onChange={(event) => setHumanAgent(event.target.checked)} disabled={busy} /></label><div className="wa-actions"><button className="button primary" onClick={saveManual} disabled={!canSaveManual}>{t("social.saveConnect")}</button></div></details>}
      {manualAvailable && channel && <section className="wa-panel"><div className="wa-panel-head"><span><Webhook size={19} /></span><div><h2>{t("social.webhookTitle")}</h2><p>{t("social.webhookCopy")}</p></div></div><div className="social-webhook-fields"><label>{t("social.webhookUrl")}<input readOnly value={channel.webhook_url} onFocus={(event) => event.currentTarget.select()} /></label><label>{t("social.verifyToken")}<input readOnly value={channel.webhook_verify_token || ""} onFocus={(event) => event.currentTarget.select()} /></label></div></section>}
    </main><aside className="wa-side"><ShieldCheck size={22} /><h3>{t("social.rulesTitle")}</h3><p>{t("social.rulesCopy")}</p><hr /><h3>{t("social.historyTitle")}</h3><p>{t("social.historyCopy")}</p></aside></div>
  </div>;
}
