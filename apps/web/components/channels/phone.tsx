"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { ArrowLeft, Bot, CheckCircle2, CircleAlert, LoaderCircle, Phone, Plug, Power, ShieldCheck, Trash2 } from "lucide-react";
import { Alert, Modal } from "@/components/ui";
import { AccountList } from "@/components/account-list";
import { api, messageFrom } from "@/lib/api";
import { accountName, accountTitle, rememberLine, requestedLine, type ChannelSetupProps } from "@/lib/channels";
import { useLanguage, type I18nKey } from "@/lib/i18n";
import type { CallAccount, CarrierNumber, PhoneLine } from "@/types";

const statusKey: Record<PhoneLine["status"], I18nKey> = {
  connected: "phone.channel.statusConnected",
  disconnected: "phone.channel.statusDisconnected",
  error: "phone.channel.statusError",
};

/** A client's phone lines, inside the client's Channels tab: one number of
 * the agency's Twilio or Telnyx account per line and the voice agent that
 * answers it, with its voice and greeting. Saving connects the line. */
export function PhoneSetup({ client, onBack }: ChannelSetupProps) {
  const { t } = useLanguage();
  const [lines, setLines] = useState<PhoneLine[]>([]);
  const [accounts, setAccounts] = useState<CallAccount[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [removing, setRemoving] = useState(false);

  const [agentId, setAgentId] = useState("");
  const [label, setLabel] = useState("");
  const [provider, setProvider] = useState<"twilio" | "telnyx">("twilio");
  const [numbers, setNumbers] = useState<CarrierNumber[] | null>(null);
  const [numberId, setNumberId] = useState("");
  const voiceAgents = client.agents.filter((agent) => agent.kind === "voice");
  const line = adding ? null : lines.find((item) => item.id === selectedId) ?? null;
  const carriers = accounts.filter((a) => a.provider !== "elevenlabs" && a.configured).map((a) => a.provider as "twilio" | "telnyx");
  const ready = accounts.some((a) => a.provider === "elevenlabs" && a.configured) && carriers.length > 0;

  const upsert = useCallback((saved: PhoneLine) => {
    setLines((items) => items.some((item) => item.id === saved.id) ? items.map((item) => (item.id === saved.id ? saved : item)) : [...items, saved]);
  }, []);

  const show = useCallback((item: PhoneLine | null) => {
    setAdding(false);
    setSelectedId(item?.id ?? null);
    setAgentId(item?.agent_id || client.agents.find((agent) => agent.kind === "voice")?.id || "");
    setLabel(item?.label || "");
    setProvider(item?.provider || "twilio");
    setNumberId(item?.provider_number_id || "");
    setError("");
    rememberLine(item?.id ?? null);
  }, [client.agents]);
  const startAdding = useCallback(() => { show(null); setAdding(true); }, [show]);

  useEffect(() => {
    Promise.all([api<PhoneLine[]>(`/phone/clients/${client.id}/lines`), api<CallAccount[]>("/phone/accounts")])
      .then(([items, accs]) => {
        setLines(items); setAccounts(accs);
        const firstCarrier = accs.find((a) => a.provider !== "elevenlabs" && a.configured);
        if (firstCarrier) setProvider(firstCarrier.provider as "twilio" | "telnyx");
        const wanted = requestedLine();
        const found = items.find((item) => item.id === wanted.line) ?? null;
        if (wanted.adding || (!found && !items.length)) startAdding(); else show(found);
      })
      .catch((err) => setError(messageFrom(err))).finally(() => setLoading(false));
  }, [client.id, show, startAdding]);

  // The carrier's numbers, for a new line; an existing line keeps its number.
  useEffect(() => {
    if (!adding || !ready) return;
    setNumbers(null);
    api<CarrierNumber[]>(`/phone/numbers?provider=${provider}`).then(setNumbers).catch((err) => { setNumbers([]); setError(messageFrom(err)); });
  }, [adding, provider, ready]);

  async function save() {
    setBusy(true); setError("");
    try {
      const common = { agent_id: agentId, label: label.trim() || null };
      let saved: PhoneLine;
      if (line) {
        saved = await api<PhoneLine>(`/phone/lines/${line.id}`, { method: "PUT", body: JSON.stringify(common) });
      } else {
        const chosen = numbers?.find((n) => n.id === numberId);
        if (!chosen) return;
        saved = await api<PhoneLine>(`/phone/clients/${client.id}/lines`, { method: "POST", body: JSON.stringify({ ...common, provider, provider_number_id: chosen.id, phone_number: chosen.phone_number }) });
      }
      upsert(saved); setAdding(false); setSelectedId(saved.id); rememberLine(saved.id);
      if (saved.last_error) setError(saved.last_error);
    } catch (err) { setError(messageFrom(err)); } finally { setBusy(false); }
  }

  async function toggle(enabled: boolean) {
    if (!line) return;
    setBusy(true); setError("");
    try { upsert(await api<PhoneLine>(`/phone/lines/${line.id}`, { method: "PUT", body: JSON.stringify({ is_enabled: enabled }) })); }
    catch (err) { setError(messageFrom(err)); } finally { setBusy(false); }
  }

  async function remove() {
    if (!line) return;
    setBusy(true); setError("");
    try {
      await api(`/phone/lines/${line.id}`, { method: "DELETE" });
      const rest = lines.filter((item) => item.id !== line.id);
      setLines(rest); setRemoving(false);
      if (rest.length) show(null); else startAdding();
    } catch (err) { setError(messageFrom(err)); } finally { setBusy(false); }
  }

  if (loading) return <div className="page-loading"><LoaderCircle className="spin" /></div>;
  const nameOf = (item: PhoneLine) => accountName(item, t("phone.channel.lineFallback", { n: lines.indexOf(item) + 1 }));
  const listView = !adding && !line;
  const agentNameOf = (item: PhoneLine) => client.agents.find((agent) => agent.id === item.agent_id)?.name || t("clients.detail.noAgent");
  const rows = lines.map((item) => ({
    id: item.id, title: item.phone_number, inboxName: nameOf(item),
    agentName: `${t("clients.detail.colAgent")}: ${agentNameOf(item)}`,
    state: item.status === "connected" && item.is_enabled ? "connected" as const : "disconnected" as const,
    stateLabel: item.is_enabled ? t(statusKey[item.status]) : t("phone.channel.off"),
  }));
  const connectedCount = rows.filter((row) => row.state === "connected").length;
  const canSave = Boolean(agentId && (line || numberId) && !busy);

  return <div className="wa-page">
    {listView || !lines.length
      ? <button type="button" className="back-link" onClick={onBack}><ArrowLeft size={17} /> {t("clients.detail.channelsBack")}</button>
      : <button type="button" className="back-link" onClick={() => show(null)}><ArrowLeft size={17} /> {t("phone.title")}</button>}
    <header className="wa-header"><div className="wa-mark"><Phone size={26} /></div><div>
      <span>{listView ? t("phone.channel.channelOf", { name: client.name }) : `${t("phone.title")} · ${client.name}`}</span>
      <h1>{line ? accountTitle(line, nameOf(line)) : adding ? t("phone.channel.newLine") : t("phone.title")}</h1>
      <p>{t("phone.channel.headerCopy")}</p></div>
      {line && <div className={`wa-state ${line.status}`}>{line.status === "connected" ? <CheckCircle2 size={17} /> : <CircleAlert size={17} />} {line.is_enabled ? t(statusKey[line.status]) : t("phone.channel.off")}</div>}
    </header>
    {!ready && <Alert>{t("phone.channel.missingAccounts")} <Link href="/settings/providers">{t("phone.channel.goToSettings")}</Link></Alert>}
    {error && <Alert>{error}</Alert>}
    {listView && <AccountList rows={rows} summary={lines.length === 1 ? t("phone.channel.lineOne") : t("phone.channel.linesSummary", { count: lines.length, connected: connectedCount })} addLabel={t("phone.channel.addLine")} openLabel={t("clients.detail.configure")} onOpen={(lineId) => show(lines.find((item) => item.id === lineId) ?? null)} onAdd={startAdding} />}
    {!listView && ready && <div className="wa-layout"><main>
      <section className="wa-panel"><div className="wa-panel-head"><span><Bot size={19} /></span><div><h2>{t("clients.whatsapp.assignedAgent")}</h2><p>{t("clients.whatsapp.assignedAgentCopy")}</p></div></div>
        <div className="wa-agent-row">
          <label>{t("clients.whatsapp.agentToRespond")}<select value={agentId} onChange={(event) => setAgentId(event.target.value)} disabled={busy}><option value="">{t("clients.whatsapp.selectAgent")}</option>{voiceAgents.map((agent) => <option key={agent.id} value={agent.id}>{agent.name}{agent.is_active ? "" : t("clients.whatsapp.inactiveSuffix")}</option>)}</select></label>
          <label>{t("clients.whatsapp.lineName")}<input value={label} maxLength={80} placeholder={t("clients.whatsapp.lineNamePlaceholder")} onChange={(event) => setLabel(event.target.value)} disabled={busy} /></label>
        </div>
        <p className="social-meta">{t("phone.channel.agentVoiceHint")}</p>
        {!voiceAgents.length && <Alert type="info">{t("phone.channel.noVoiceAgents")} <Link href={`/agents/new?client=${client.id}&kind=voice`}>{t("phone.channel.createVoiceAgent")}</Link></Alert>}
      </section>

      <section className="wa-panel"><div className="wa-panel-head"><span><Phone size={19} /></span><div><h2>{t("phone.channel.numberTitle")}</h2><p>{t("phone.channel.numberCopy")}</p></div></div>
        {line ? <p className="phone-line-number"><strong>{line.phone_number}</strong> · {line.provider === "twilio" ? "Twilio" : "Telnyx"}</p> : <div className="wa-agent-row">
          <label>{t("phone.channel.carrier")}<select value={provider} onChange={(event) => { setProvider(event.target.value as "twilio" | "telnyx"); setNumberId(""); }} disabled={busy}>{carriers.map((c) => <option key={c} value={c}>{c === "twilio" ? "Twilio" : "Telnyx"}</option>)}</select></label>
          <label>{t("phone.channel.number")}{numbers === null ? <span className="field-help"><LoaderCircle className="spin" size={14} /></span>
            : <select value={numberId} onChange={(event) => setNumberId(event.target.value)} disabled={busy || !numbers.length}><option value="">{t("phone.channel.selectNumber")}</option>{numbers.map((n) => <option key={n.id} value={n.id}>{n.phone_number}{n.name && n.name !== n.phone_number ? ` · ${n.name}` : ""}</option>)}</select>}</label>
        </div>}
        {!line && numbers?.length === 0 && <p className="social-meta">{t("phone.channel.noNumbers")}</p>}
      </section>

      {line?.status === "connected" && line.is_enabled && <div className="wa-connected"><div className="wa-ready"><CheckCircle2 size={18} /> {t("phone.channel.connectedCopy", { number: line.phone_number, agent: agentNameOf(line) })}</div></div>}
      {line && <label className="switch-row"><span><strong>{t("phone.channel.enabled")}</strong><small>{t("phone.channel.enabledHint")}</small></span><input type="checkbox" checked={line.is_enabled} disabled={busy} onChange={(event) => toggle(event.target.checked)} /></label>}
      <div className="wa-actions">
        {line && <div className="wa-actions-side"><button className="button quiet" onClick={() => setRemoving(true)} disabled={busy}><Trash2 size={16} /> {t("phone.channel.remove")}</button></div>}
        <button className="button primary" onClick={save} disabled={!canSave}>{busy ? <LoaderCircle className="spin" size={17} /> : line?.status === "connected" ? <Power size={17} /> : <Plug size={17} />} {line && line.status !== "connected" ? t("phone.channel.reconnect") : t("phone.channel.save")}</button>
      </div>
    </main><aside className="wa-side"><ShieldCheck size={22} /><h3>{t("clients.whatsapp.separationTitle")}</h3><p>{t("clients.whatsapp.separationCopy")}<strong>{client.name}</strong>.</p></aside></div>}
    <Modal open={removing && Boolean(line)} title={t("phone.channel.removeTitle", { name: line ? nameOf(line) : "" })} onClose={() => setRemoving(false)}>
      <div className="modal-form">
        <p className="modal-copy">{t("phone.channel.removeCopy")}</p>
        <div className="modal-actions"><button type="button" className="button" onClick={() => setRemoving(false)}>{t("common.cancel")}</button><button type="button" className="button danger" disabled={busy} onClick={remove}>{busy ? <LoaderCircle className="spin" size={16} /> : <><Trash2 size={15} /> {t("phone.channel.remove")}</>}</button></div>
      </div>
    </Modal>
  </div>;
}
