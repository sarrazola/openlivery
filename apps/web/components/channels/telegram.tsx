"use client";

import { useCallback, useEffect, useState } from "react";
import { ArrowLeft, Bot, CheckCircle2, CircleAlert, ExternalLink, KeyRound, LoaderCircle, MessagesSquare, Plug, Power, Send, ShieldCheck } from "lucide-react";
import { Alert, Modal } from "@/components/ui";
import { AccountList } from "@/components/account-list";
import { api, messageFrom } from "@/lib/api";
import { accountName, accountTitle, rememberLine, requestedLine, type ChannelSetupProps } from "@/lib/channels";
import { useT } from "@/lib/i18n";
import type { Client, TelegramChannel } from "@/types";

/** A client's Telegram bots, inside the client's Channels tab. The view opens
 * on the list of bots; one is picked from there (or named by `?line=<id>`)
 * and the panels below then configure it. `?new`, or an empty list, adds
 * another with the token @BotFather issued for it. */
export function TelegramSetup({ client, onBack }: ChannelSetupProps) {
  const t = useT();
  const [bots, setBots] = useState<TelegramChannel[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [agentId, setAgentId] = useState("");
  const [label, setLabel] = useState("");
  const [token, setToken] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const [disconnectOpen, setDisconnectOpen] = useState(false);
  const bot = adding ? null : bots.find((item) => item.id === selectedId) ?? null;

  const apply = useCallback((current: TelegramChannel) => {
    setBots((items) => items.some((item) => item.id === current.id) ? items.map((item) => item.id === current.id ? current : item) : [...items, current]);
    setAdding(false); setSelectedId(current.id); rememberLine(current.id);
    setAgentId(current.agent_id); setLabel(current.label || ""); setToken("");
  }, []);

  const showList = useCallback(() => {
    setAdding(false); setSelectedId(null); rememberLine(null); setError(""); setSaved(false);
  }, []);

  const startAdding = useCallback((owner: Client) => {
    setAdding(true); setSelectedId(null); rememberLine(null);
    setAgentId(owner.agents[0]?.id || ""); setLabel(""); setToken(""); setError(""); setSaved(false);
  }, []);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const items = await api<TelegramChannel[]>(`/telegram/clients/${client.id}/channels`);
      setBots(items);
      const wanted = requestedLine();
      const line = items.find((item) => item.id === wanted.line) ?? null;
      if (wanted.adding || (!line && !items.length)) startAdding(client);
      else if (line) apply(line);
      else showList();
    } catch (err) { setError(messageFrom(err)); }
    finally { setLoading(false); }
  }, [client, apply, startAdding, showList]);
  useEffect(() => { void load(); }, [load]);

  async function run(action: () => Promise<void>) {
    setBusy(true); setError(""); setSaved(false);
    try { await action(); }
    catch (err) { setError(messageFrom(err)); }
    finally { setBusy(false); }
  }

  const connect = () => run(async () => {
    apply(await api<TelegramChannel>(`/telegram/clients/${client.id}/channels`, {
      method: "POST", body: JSON.stringify({ agent_id: agentId, token: token.trim(), label: label.trim() || null }),
    }));
    setSaved(true);
  });

  const save = () => run(async () => {
    if (!bot) return;
    const body: Record<string, string> = { agent_id: agentId, label: label.trim() };
    if (token.trim()) body.token = token.trim();
    apply(await api<TelegramChannel>(`/telegram/channels/${bot.id}`, { method: "PATCH", body: JSON.stringify(body) }));
    setSaved(true);
  });

  const verify = () => run(async () => {
    if (!bot) return;
    apply(await api<TelegramChannel>(`/telegram/channels/${bot.id}/connect`, { method: "POST" }));
    setSaved(true);
  });

  const disconnect = () => run(async () => {
    if (!bot) return;
    await api(`/telegram/channels/${bot.id}/disconnect`, { method: "POST" });
    const rest = bots.filter((item) => item.id !== bot.id);
    setBots(rest); setDisconnectOpen(false);
    if (rest.length) showList(); else startAdding(client);
  });

  if (loading) return <div className="page-loading"><LoaderCircle className="spin" /> {t("social.loading")}</div>;
  const listView = !adding && !bot;
  const connected = Boolean(bot && bot.status === "connected" && bot.is_enabled);
  const nameOf = (item: TelegramChannel) => accountName(item, t("telegram.botFallback", { n: bots.indexOf(item) + 1 }));
  const agentNameOf = (item: TelegramChannel) => client.agents.find((agent) => agent.id === item.agent_id)?.name || t("clients.detail.noAgent");
  const rows = bots.map((item) => {
    const live = item.is_enabled && item.status === "connected";
    return {
      id: item.id, title: item.username ? `@${item.username}` : item.display_name || nameOf(item), inboxName: nameOf(item),
      agentName: `${t("clients.detail.colAgent")}: ${agentNameOf(item)}`,
      state: live ? "connected" as const : "disconnected" as const,
      stateLabel: t(live ? "telegram.connected" : "telegram.disconnected"),
    };
  });
  const connectedCount = rows.filter((row) => row.state === "connected").length;
  const dirty = Boolean(bot && (bot.agent_id !== agentId || (bot.label || "") !== label.trim() || token.trim()));
  const canConnect = Boolean(agentId && token.trim()) && !busy;

  return <div className="wa-page social-page">
    {listView || !bots.length
      ? <button type="button" className="back-link" onClick={onBack}><ArrowLeft size={17} /> {t("clients.detail.channelsBack")}</button>
      : <button type="button" className="back-link" onClick={showList}><ArrowLeft size={17} /> {t("telegram.title")}</button>}
    <header className="wa-header"><div className="wa-mark telegram"><Send size={26} /></div><div><span>{listView ? t("clients.whatsapp.channelOf", { name: client.name }) : `${t("telegram.title")} · ${client.name}`}</span><h1>{bot ? accountTitle(bot, nameOf(bot)) : adding ? t("telegram.newBot") : t("telegram.title")}</h1><p>{t("telegram.description")}</p></div>{bot && <div className={`wa-state ${connected ? "connected" : "disconnected"}`}>{connected ? <CheckCircle2 size={17} /> : <CircleAlert size={17} />} {t(connected ? "telegram.connected" : "telegram.disconnected")}</div>}</header>
    {error && <Alert>{error}</Alert>}
    {listView && <AccountList rows={rows} summary={bots.length === 1 ? t("clients.detail.channelAccountOne") : t("clients.detail.channelAccounts", { count: bots.length, connected: connectedCount })} addLabel={t("clients.detail.addAccount")} openLabel={t("clients.detail.configure")} onOpen={(id) => { const item = bots.find((line) => line.id === id); if (item) { apply(item); setError(""); setSaved(false); } }} onAdd={() => startAdding(client)} />}
    {saved && <p className="social-feedback" role="status"><CheckCircle2 size={16} /> {t("telegram.saved")}</p>}
    {!listView && <div className="wa-layout"><main>
      <section className="wa-panel"><div className="wa-panel-head"><span><Bot size={19} /></span><div><h2>{t("clients.whatsapp.assignedAgent")}</h2><p>{t("clients.whatsapp.assignedAgentCopy")}</p></div></div>
        <div className="wa-agent-row"><label>{t("clients.whatsapp.agentToRespond")}<select value={agentId} onChange={(event) => setAgentId(event.target.value)} disabled={busy}><option value="">{t("clients.whatsapp.selectAgent")}</option>{client.agents.map((agent) => <option key={agent.id} value={agent.id}>{agent.name}{agent.is_active ? "" : t("clients.whatsapp.inactiveSuffix")}</option>)}</select></label><label>{t("telegram.accountName")}<input value={label} maxLength={80} placeholder={t("telegram.accountNamePlaceholder")} onChange={(event) => setLabel(event.target.value)} disabled={busy} /></label></div>
        <p className="social-meta">{t("telegram.accountNameHint")}</p>
        {!client.agents.length && <Alert>{t("telegram.needsAgent")}</Alert>}
      </section>
      {bot && <section className="wa-panel"><div className="wa-panel-head"><span><Send size={19} /></span><div><h2>{t("telegram.botTitle")}</h2><p>{t("telegram.botCopy")}</p></div></div>
        <div className="social-account"><Send size={24} /><div><strong>{bot.display_name || bot.username || bot.external_account_id}</strong>{bot.username && <small>@{bot.username}</small>}{connected && <small>{t("telegram.connectedCopy")}</small>}</div></div>
        {bot.status === "reauthorization_required" ? <Alert>{t("telegram.needsToken")}</Alert> : bot.last_error && <Alert>{bot.last_error}</Alert>}
        <p className="social-meta">{t("telegram.groupsNote")}</p>
        <div className="wa-actions">{bot.username && <a className="button secondary" href={`https://t.me/${bot.username}`} target="_blank" rel="noreferrer"><ExternalLink size={16} /> {t("telegram.openChat")}</a>}<button className="button secondary" disabled={busy} onClick={verify}><Plug size={16} /> {t("telegram.verify")}</button><button className="button danger" onClick={() => setDisconnectOpen(true)} disabled={busy}><Power size={16} /> {t("telegram.disconnect")}</button></div>
        <Modal open={disconnectOpen} title={t("telegram.disconnectTitle", { name: bot.username ? `@${bot.username}` : bot.display_name || "" })} onClose={() => setDisconnectOpen(false)}>
          <div className="modal-form">
            <p className="modal-copy">{t("telegram.disconnectCopy")}</p>
            <div className="modal-actions"><button type="button" className="button" onClick={() => setDisconnectOpen(false)}>{t("common.cancel")}</button><button type="button" className="button danger" disabled={busy} onClick={disconnect}>{busy ? <LoaderCircle className="spin" size={16} /> : <><Power size={15} /> {t("telegram.disconnect")}</>}</button></div>
          </div>
        </Modal>
      </section>}
      <section className="wa-panel"><div className="wa-panel-head"><span><KeyRound size={19} /></span><div><h2>{t("telegram.tokenTitle")}</h2><p>{t("telegram.tokenCopy")}</p></div></div>
        <div className="wa-cloud-form"><label className="telegram-token">{t("telegram.tokenLabel")}<input type="password" value={token} onChange={(event) => setToken(event.target.value)} placeholder={bot?.has_token ? t("telegram.tokenSaved") : "123456789:AA…"} disabled={busy} autoComplete="new-password" spellCheck={false} /></label></div>
        <div className="wa-actions">
          {bot
            ? <button className="button primary" disabled={!agentId || !dirty || busy} onClick={save}>{busy ? <LoaderCircle className="spin" size={17} /> : <CheckCircle2 size={17} />} {t(token.trim() ? "telegram.replaceToken" : "telegram.save")}</button>
            : <button className="button primary" disabled={!canConnect} onClick={connect}>{busy ? <LoaderCircle className="spin" size={17} /> : <Plug size={17} />} {t("telegram.connect")}</button>}
        </div>
      </section>
    </main><aside className="wa-side"><ShieldCheck size={22} /><h3>{t("telegram.rulesTitle")}</h3><p>{t("telegram.rulesCopy")}</p><hr /><h3><MessagesSquare size={16} /> {t("telegram.mediaTitle")}</h3><p>{t("telegram.mediaCopy")}</p></aside></div>}
  </div>;
}
