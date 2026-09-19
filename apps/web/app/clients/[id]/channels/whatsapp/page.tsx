"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { ArrowLeft, Bot, CheckCircle2, CircleAlert, LoaderCircle, MessageCircle, Plug, Power, QrCode, RefreshCw, ShieldCheck, Smartphone, Trash2 } from "lucide-react";
import { Alert, Modal } from "@/components/ui";
import { AccountList } from "@/components/account-list";
import { ConfirmModal } from "@/components/confirm-modal";
import { api, messageFrom } from "@/lib/api";
import { accountName, accountTitle, rememberLine, requestedLine } from "@/lib/channels";
import { useT, type I18nKey } from "@/lib/i18n";
import type { Client, WhatsAppChannel } from "@/types";

const stateKeys: Record<WhatsAppChannel["status"], { label: I18nKey; copy: I18nKey }> = {
  disconnected: { label: "clients.whatsapp.statusDisconnectedLabel", copy: "clients.whatsapp.statusDisconnectedCopy" },
  connecting: { label: "clients.whatsapp.statusConnectingLabel", copy: "clients.whatsapp.statusConnectingCopy" },
  qr: { label: "clients.whatsapp.statusQrLabel", copy: "clients.whatsapp.statusQrCopy" },
  connected: { label: "clients.whatsapp.statusConnectedLabel", copy: "clients.whatsapp.statusConnectedCopy" },
  reconnecting: { label: "clients.whatsapp.statusReconnectingLabel", copy: "clients.whatsapp.statusReconnectingCopy" },
  error: { label: "clients.whatsapp.statusErrorLabel", copy: "clients.whatsapp.statusErrorCopy" },
};

/** A client's WhatsApp QR lines. The page opens on the list of them; one is
 * picked from there (or named by `?line=<id>`) and the panels below then
 * configure that one. `?new`, or an empty list, starts another. */
export default function WhatsAppChannelPage() {
  const t = useT();
  const { id } = useParams<{ id: string }>();
  const [client, setClient] = useState<Client | null>(null);
  const [lines, setLines] = useState<WhatsAppChannel[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [agentId, setAgentId] = useState("");
  const [label, setLabel] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [removing, setRemoving] = useState(false);
  const [disconnecting, setDisconnecting] = useState(false);
  const channel = adding ? null : lines.find((line) => line.id === selectedId) ?? null;

  const upsert = useCallback((saved: WhatsAppChannel) => {
    setLines((items) => items.some((item) => item.id === saved.id) ? items.map((item) => (item.id === saved.id ? saved : item)) : [...items, saved]);
  }, []);

  /** Open one line, or with `null` the list of them. */
  const show = useCallback((line: WhatsAppChannel | null, owner: Client | null) => {
    setAdding(false);
    setSelectedId(line?.id ?? null);
    setAgentId(line?.agent_id || owner?.agents[0]?.id || "");
    setLabel(line?.label || "");
    setError("");
    rememberLine(line?.id ?? null);
  }, []);
  const startAdding = useCallback((owner: Client | null) => { show(null, owner); setAdding(true); }, [show]);

  useEffect(() => {
    Promise.all([api<Client>(`/clients/${id}`), api<WhatsAppChannel[]>(`/whatsapp/clients/${id}/channels`)])
      .then(([owner, items]) => {
        setClient(owner); setLines(items);
        const wanted = requestedLine();
        const line = items.find((item) => item.id === wanted.line) ?? null;
        if (wanted.adding || (!line && !items.length)) startAdding(owner); else show(line, owner);
      })
      .catch((err) => setError(messageFrom(err))).finally(() => setLoading(false));
  }, [id, show, startAdding]);

  // The selected line is polled while it exists: the QR and the connection state come from the bridge.
  const channelId = channel?.id ?? null;
  useEffect(() => {
    if (!channelId) return;
    const timer = window.setInterval(() => { api<WhatsAppChannel>(`/whatsapp/channels/${channelId}`).then(upsert).catch((err) => setError(messageFrom(err))); }, 2500);
    return () => window.clearInterval(timer);
  }, [channelId, upsert]);

  async function save(): Promise<WhatsAppChannel> {
    const body = JSON.stringify({ agent_id: agentId, label: label.trim() });
    const saved = channel
      ? await api<WhatsAppChannel>(`/whatsapp/channels/${channel.id}`, { method: "PUT", body })
      : await api<WhatsAppChannel>(`/whatsapp/clients/${id}/channels`, { method: "POST", body });
    upsert(saved); setAdding(false); setSelectedId(saved.id); rememberLine(saved.id);
    return saved;
  }

  async function saveAndConnect() {
    if (!agentId) return;
    setBusy(true); setError("");
    try {
      const saved = await save();
      upsert(await api<WhatsAppChannel>(`/whatsapp/channels/${saved.id}/connect`, { method: "POST" }));
    } catch (err) { setError(messageFrom(err)); } finally { setBusy(false); }
  }

  async function saveDetails() {
    setBusy(true); setError("");
    try { await save(); } catch (err) { setError(messageFrom(err)); } finally { setBusy(false); }
  }

  async function disconnect() {
    if (!channel) return;
    upsert(await api<WhatsAppChannel>(`/whatsapp/channels/${channel.id}/disconnect`, { method: "POST" }));
  }

  async function remove() {
    if (!channel) return;
    setBusy(true); setError("");
    try {
      await api(`/whatsapp/channels/${channel.id}`, { method: "DELETE" });
      const rest = lines.filter((line) => line.id !== channel.id);
      setLines(rest); setRemoving(false);
      if (rest.length) show(null, client); else startAdding(client);
    } catch (err) { setError(messageFrom(err)); } finally { setBusy(false); }
  }

  if (loading || !client) return <div className="page-loading"><LoaderCircle className="spin" /> {t("clients.whatsapp.loading")}</div>;
  const state = stateKeys[channel?.status || "disconnected"];
  const canConnect = Boolean(agentId && !busy && channel?.status !== "connected");
  const dirty = Boolean(channel && (channel.agent_id !== agentId || (channel.label || "") !== label.trim()));
  const nameOf = (line: WhatsAppChannel) => accountName(line, t("clients.whatsapp.lineFallback", { n: lines.indexOf(line) + 1 }));
  const listView = !adding && !channel;
  const agentNameOf = (line: WhatsAppChannel) => client.agents.find((agent) => agent.id === line.agent_id)?.name || t("clients.detail.noAgent");
  const rows = lines.map((line) => ({
    id: line.id, title: line.phone_number ? `+${line.phone_number}` : nameOf(line), inboxName: nameOf(line),
    agentName: `${t("clients.detail.colAgent")}: ${agentNameOf(line)}`,
    state: line.status === "connected" ? "connected" as const : ["qr", "connecting", "reconnecting"].includes(line.status) ? "pending" as const : "disconnected" as const,
    stateLabel: t(stateKeys[line.status].label),
  }));
  const connectedCount = lines.filter((line) => line.status === "connected").length;
  return <div className="page wa-page">
    {listView || !lines.length
      ? <Link href={`/clients/${client.id}?tab=channels`} className="back-link"><ArrowLeft size={17} /> {t("clients.whatsapp.back", { name: client.name })}</Link>
      : <button type="button" className="back-link" onClick={() => show(null, client)}><ArrowLeft size={17} /> {t("clients.whatsapp.title")}</button>}
    <header className="wa-header"><div className="wa-mark"><MessageCircle size={26} /></div><div><span>{listView ? t("clients.whatsapp.channelOf", { name: client.name }) : `${t("clients.whatsapp.title")} · ${client.name}`}</span><h1>{channel ? accountTitle(channel, nameOf(channel)) : adding ? t("clients.whatsapp.newLine") : t("clients.whatsapp.title")}</h1><p>{t("clients.whatsapp.headerCopy")}</p></div>{channel && <div className={`wa-state ${channel.status}`}>{channel.status === "connected" ? <CheckCircle2 size={17} /> : channel.status === "error" ? <CircleAlert size={17} /> : <RefreshCw className={["connecting", "reconnecting"].includes(channel.status) ? "spin" : ""} size={17} />} {t(state.label)}</div>}</header>
    {error && <Alert>{error}</Alert>}
    {listView && <AccountList rows={rows} summary={lines.length === 1 ? t("clients.detail.channelNumberOne") : t("clients.detail.channelNumbers", { count: lines.length, connected: connectedCount })} addLabel={t("clients.detail.addNumber")} openLabel={t("clients.detail.configure")} onOpen={(lineId) => show(lines.find((line) => line.id === lineId) ?? null, client)} onAdd={() => startAdding(client)} />}
    {!listView && <div className="wa-layout"><main>
      <section className="wa-panel"><div className="wa-panel-head"><span><Bot size={19} /></span><div><h2>{t("clients.whatsapp.assignedAgent")}</h2><p>{t("clients.whatsapp.assignedAgentCopy")}</p></div></div><div className="wa-agent-row"><label>{t("clients.whatsapp.agentToRespond")}<select value={agentId} onChange={(event) => setAgentId(event.target.value)} disabled={busy}><option value="">{t("clients.whatsapp.selectAgent")}</option>{client.agents.map((agent) => <option key={agent.id} value={agent.id}>{agent.name}{agent.is_active ? "" : t("clients.whatsapp.inactiveSuffix")}</option>)}</select></label><label>{t("clients.whatsapp.lineName")}<input value={label} maxLength={80} placeholder={t("clients.whatsapp.lineNamePlaceholder")} onChange={(event) => setLabel(event.target.value)} disabled={busy} /></label>{dirty && <button className="button secondary" onClick={saveDetails} disabled={!agentId || busy}>{t("common.save")}</button>}</div><p className="social-meta">{t("clients.whatsapp.lineNameHint")}</p>{!client.agents.length && <Alert>{t("clients.whatsapp.needsAgent")}</Alert>}</section>
      <section className="wa-panel"><div className="wa-panel-head"><span><Plug size={19} /></span><div><h2>{t("clients.whatsapp.connection")}</h2><p>{t(state.copy)}</p></div></div>
        {channel?.status === "qr" && channel.qr_code && <div className="wa-qr"><img src={channel.qr_code} alt={t("clients.whatsapp.qrAlt")} /><div><span><QrCode size={18} /> {t("clients.whatsapp.scanFromPhone")}</span><ol><li>{t("clients.whatsapp.qrStep1")}</li><li>{t("clients.whatsapp.qrStep2Prefix")}<strong>{t("clients.whatsapp.qrStep2Bold")}</strong>.</li><li>{t("clients.whatsapp.qrStep3Prefix")}<strong>{t("clients.whatsapp.qrStep3Bold")}</strong>{t("clients.whatsapp.qrStep3Suffix")}</li></ol><small>{t("clients.whatsapp.qrHint")}</small></div></div>}
        {channel?.status === "connected" && <div className="wa-connected"><div className="wa-phone"><Smartphone size={24} /><span><small>{t("clients.whatsapp.connectedNumber")}</small><strong>{channel.phone_number ? `+${channel.phone_number}` : t("clients.whatsapp.linkedNumber")}</strong>{channel.display_name && <em>{channel.display_name}</em>}</span></div><div className="wa-ready"><CheckCircle2 size={18} /> {t("clients.whatsapp.readyForMessages")}</div></div>}
        {channel?.last_error && <Alert>{channel.last_error}</Alert>}
        <div className="wa-actions">{channel && <button className="button quiet" onClick={() => setRemoving(true)} disabled={busy}><Trash2 size={16} /> {t("clients.whatsapp.removeLine")}</button>}{channel?.status === "connected" ? <button className="button danger" onClick={() => setDisconnecting(true)} disabled={busy}><Power size={17} /> {t("clients.whatsapp.disconnectAccount")}</button> :<button className="button primary" onClick={saveAndConnect} disabled={!canConnect}>{busy || ["connecting", "reconnecting"].includes(channel?.status || "") ? <LoaderCircle className="spin" size={17} /> : <QrCode size={17} />} {channel?.has_session ? t("clients.whatsapp.recoverConnection") : t("clients.whatsapp.connectWithQr")}</button>}</div>
      </section>
    </main><aside className="wa-side"><ShieldCheck size={22} /><h3>{t("clients.whatsapp.separationTitle")}</h3><p>{t("clients.whatsapp.separationCopy")}<strong>{client.name}</strong>.</p><hr /><h3>{t("clients.whatsapp.humanControlTitle")}</h3><p>{t("clients.whatsapp.humanControlCopy")}</p></aside></div>}
    {disconnecting && channel && <ConfirmModal title={t("clients.whatsapp.disconnectAccount")} message={t("clients.whatsapp.confirmDisconnect")} confirmLabel={t("clients.whatsapp.disconnectAccount")} cancelLabel={t("common.cancel")} confirmIcon={<Power size={15} />} onConfirm={disconnect} onClose={() => setDisconnecting(false)} />}
    <Modal open={removing && Boolean(channel)} title={t("clients.whatsapp.removeLineTitle", { name: channel ? nameOf(channel) : "" })} onClose={() => setRemoving(false)}>
      <div className="modal-form">
        <p className="modal-copy">{t("clients.whatsapp.removeLineCopy")}</p>
        <div className="modal-actions"><button type="button" className="button" onClick={() => setRemoving(false)}>{t("common.cancel")}</button><button type="button" className="button danger" disabled={busy} onClick={remove}>{busy ? <LoaderCircle className="spin" size={16} /> : <><Trash2 size={15} /> {t("clients.whatsapp.removeLine")}</>}</button></div>
      </div>
    </Modal>
  </div>;
}
