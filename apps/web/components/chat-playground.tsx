"use client";

import Link from "next/link";
import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { Bot, FileText, LoaderCircle, MessageSquarePlus, Send, Sparkles, TriangleAlert, UserRound, Wrench } from "lucide-react";
import { api, apiUrl, messageFrom } from "@/lib/api";
import { AttachButton, MessageAttachments, PendingAttachment, RecordButton, useFileDrop, type GalleryImage } from "@/components/attachments";
import { RichText } from "@/components/rich-text";
import { Alert, EmptyState } from "@/components/ui";
import { ListRowsSkeleton } from "@/components/skeleton";
import { useToast } from "@/components/toast";
import { useT } from "@/lib/i18n";
import type { Agent, Attachment, Client, Conversation, Provider } from "@/types";

export function ChatPlayground({ lockedAgentId }: { lockedAgentId?: string }) {
  const t = useT();
  const toast = useToast();
  const [clients, setClients] = useState<Client[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [clientId, setClientId] = useState("");
  const [agentId, setAgentId] = useState(lockedAgentId || "");
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [conversation, setConversation] = useState<Conversation | null>(null);
  const [providers, setProviders] = useState<Provider[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const composerRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    Promise.all([api<Client[]>("/clients"), api<Agent[]>("/agents"), api<Provider[]>("/providers")]).then(([c, a, p]) => {
      setClients(c); setAgents(a); setProviders(p);
      const initial = lockedAgentId ? a.find((item) => item.id === lockedAgentId) : a[0];
      if (initial) { setAgentId(initial.id); setClientId(initial.client_id); }
      else if (c[0]) setClientId(c[0].id);
    }).catch(() => {}).finally(() => setLoaded(true));
  }, [lockedAgentId]);

  useEffect(() => {
    if (!agentId) { setConversations([]); setConversation(null); return; }
    api<Conversation[]>(`/conversations?agent_id=${agentId}`).then((items) => {
      setConversations(items);
      if (items[0]) api<Conversation>(`/conversations/${items[0].id}`).then(setConversation);
      else setConversation(null);
    });
  }, [agentId]);
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [conversation?.messages?.length]);

  const availableAgents = useMemo(() => agents.filter((agent) => agent.client_id === clientId), [agents, clientId]);
  const selectedAgent = agents.find((agent) => agent.id === agentId);
  const needsKey = Boolean(selectedAgent) && !providers.find((item) => item.provider === selectedAgent!.provider)?.configured;
  const needsModel = Boolean(selectedAgent) && !selectedAgent!.model.trim();
  const agentReady = Boolean(selectedAgent) && !needsKey && !needsModel;

  async function newConversation() {
    if (!agentId) return;
    const created = await api<Conversation>("/conversations", { method: "POST", body: JSON.stringify({ agent_id: agentId }) });
    setConversation(created); setConversations((items) => [created, ...items]);
  }
  async function chooseConversation(item: Conversation) {
    setConversation(await api<Conversation>(`/conversations/${item.id}`));
  }
  async function send(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pendingFile) {
      const file = pendingFile;
      setPendingFile(null);
      await sendFile(file);
      return;
    }
    const form = event.currentTarget;
    const input = form.elements.namedItem("message") as HTMLTextAreaElement;
    const content = input.value.trim();
    if (!content || busy || !agentId || !agentReady) return;
    setBusy(true); input.value = "";
    try {
      let current = conversation;
      if (!current) {
        current = await api<Conversation>("/conversations", { method: "POST", body: JSON.stringify({ agent_id: agentId }) });
      }
      const optimistic = { ...current, messages: [...(current.messages || []), { id: "temp", role: "user" as const, content, sources: [], sender_type: "visitor" as const, sender_name: t("playground.message.you"), created_at: new Date().toISOString() }] };
      setConversation(optimistic);
      const updated = await api<Conversation>(`/conversations/${current.id}/messages`, { method: "POST", body: JSON.stringify({ content }) });
      setConversation(updated);
      setConversations(await api<Conversation[]>(`/conversations?agent_id=${agentId}`));
    } catch (err) { toast.error(messageFrom(err)); } finally { setBusy(false); composerRef.current?.focus(); }
  }
  async function sendFile(file?: File) {
    if (!file || busy || !agentId || !agentReady) return;
    setBusy(true);
    const caption = (composerRef.current?.value || "").trim();
    try {
      let current = conversation;
      if (!current) {
        current = await api<Conversation>("/conversations", { method: "POST", body: JSON.stringify({ agent_id: agentId }) });
      }
      const data = new FormData();
      data.append("file", file);
      if (caption) data.append("caption", caption);
      const updated = await api<Conversation>(`/conversations/${current.id}/media`, { method: "POST", body: data });
      if (composerRef.current) composerRef.current.value = "";
      setConversation(updated);
      setConversations(await api<Conversation[]>(`/conversations?agent_id=${agentId}`));
    } catch (err) { toast.error(messageFrom(err)); } finally { setBusy(false); }
  }
  const { dropProps, overlay } = useFileDrop(setPendingFile, { enabled: Boolean(agentId) && agentReady && !busy, label: t("chat.dropToSend") });
  const attachmentUrl = (attachment: Attachment) => apiUrl(`/conversations/${conversation?.id}/attachments/${attachment.id}`);
  const gallery: GalleryImage[] = useMemo(
    () => (conversation?.messages ?? []).flatMap((message) =>
      (message.attachments ?? []).filter((a) => a.kind === "image").map((a) => ({ id: a.id, url: apiUrl(`/conversations/${conversation?.id}/attachments/${a.id}`), name: a.filename }))
    ),
    [conversation],
  );

  return <div className={`playground-layout ${lockedAgentId ? "embedded" : ""}`}>
    <aside className="conversation-sidebar">
      {!lockedAgentId && <div className="playground-selectors"><label>{t("playground.selectors.client")}<select value={clientId} onChange={(e) => { setClientId(e.target.value); const first = agents.find((a) => a.client_id === e.target.value); setAgentId(first?.id || ""); }}>{clients.map((client) => <option key={client.id} value={client.id}>{client.name}</option>)}</select></label><label>{t("playground.selectors.agent")}<select value={agentId} onChange={(e) => setAgentId(e.target.value)}><option value="">{t("playground.selectors.agentPlaceholder")}</option>{availableAgents.map((agent) => <option key={agent.id} value={agent.id}>{agent.name}</option>)}</select></label></div>}
      <div className="conversation-head"><strong>{t("playground.conversations.heading")}</strong><button className="icon-button" onClick={newConversation} disabled={!agentId} title={t("playground.conversations.new")}><MessageSquarePlus size={17} /></button></div>
      <div className="conversation-list">{conversations.map((item) => <button key={item.id} className={conversation?.id === item.id ? "active" : ""} onClick={() => chooseConversation(item)}><MessageSquarePlus size={15} /><span><strong>{item.title}</strong><small>{new Date(item.updated_at).toLocaleDateString("es", { day: "numeric", month: "short" })}</small></span></button>)}{agentId && !conversations.length && <small className="no-conversations">{t("playground.conversations.empty")}</small>}</div>
    </aside>
    <section className="chat-panel drop-target" {...dropProps}>
      {overlay}
      <header className="chat-head">{selectedAgent ? <><span className="agent-avatar"><Bot size={18} /></span><div><strong>{selectedAgent.name}</strong><small><i className={selectedAgent.model ? "online" : "offline"} />{selectedAgent.model ? t("playground.chat.modelConfigured") : t("playground.chat.noModelConfigured")}</small></div></> : <div><strong>{t("playground.chat.fallbackTitle")}</strong><small>{t("playground.chat.fallbackSubtitle")}</small></div>}{conversation && <span className={`mode-label ${conversation.mode}`}>{conversation.mode === "human" ? t("playground.chat.modeHuman") : t("playground.chat.modeAi")}</span>}</header>
      <div className="messages">
        {!loaded ? <ListRowsSkeleton rows={4} /> : !agentId ? <EmptyState icon={<Bot />} title={t("playground.empty.title")} description={t("playground.empty.description")} /> : !conversation?.messages?.length ? <div className="chat-welcome"><span><Sparkles size={24} /></span><h3>{t("playground.welcome.title", { name: selectedAgent?.name || "" })}</h3><p>{t("playground.welcome.description")}</p></div> : conversation.messages.map((message) => <div className={`message-row ${message.role}`} key={message.id}><span className="message-avatar">{message.role === "assistant" ? <Bot size={17} /> : <UserRound size={17} />}</span><div className="message-body"><small>{message.sender_name || (message.role === "assistant" ? selectedAgent?.name : t("playground.message.you"))}</small><MessageAttachments attachments={message.attachments} urlFor={attachmentUrl} gallery={gallery} />{message.content && <div className="bubble"><RichText text={message.content} /></div>}{message.sources?.length > 0 && <div className="sources"><strong><FileText size={13} /> {t("playground.message.sourcesUsed")}</strong>{message.sources.map((source) => <span key={source.id} title={source.excerpt}>{source.filename}</span>)}</div>}{(message.tool_calls?.length ?? 0) > 0 && <div className="sources"><strong><Wrench size={13} /> {t("tools.usedInReply")}</strong>{message.tool_calls!.map((call, index) => <span key={index} className={call.is_error ? "tool-error" : ""} title={call.result_preview}>{call.name}</span>)}</div>}{message.tool_calls?.some((call) => call.is_error) && <div className="tool-error-details">{message.tool_calls!.filter((call) => call.is_error).map((call, index) => <small key={index}><TriangleAlert size={12} /> <strong>{call.name}</strong> {call.result_preview}</small>)}</div>}</div></div>)}
        {busy && <div className="message-row assistant"><span className="message-avatar"><Bot size={17} /></span><div className="thinking"><i /><i /><i /></div></div>}
        <div ref={endRef} />
      </div>
      <div className="composer-wrap">{needsKey ? <Alert type="info">{t("playground.notReady.keyPrefix")}<Link href="/settings">{t("playground.notReady.settingsLink")}</Link>.</Alert> : needsModel ? <Alert type="info">{t("playground.notReady.modelPrefix")}<Link href={`/agents/${agentId}`}>{t("playground.notReady.modelLink")}</Link>.</Alert> : null}{pendingFile && <PendingAttachment file={pendingFile} onCancel={() => setPendingFile(null)} />}<form className="composer" onSubmit={send}><AttachButton onFile={setPendingFile} disabled={!agentId || busy || !agentReady} title={t("chat.attachFile")} /><RecordButton onRecorded={sendFile} onError={() => toast.error(t("chat.micDenied"))} disabled={!agentId || busy || !agentReady} title={t("chat.recordAudio")} titleStop={t("chat.stopRecording")} /><textarea ref={composerRef} name="message" rows={1} placeholder={agentId ? t("playground.composer.placeholder") : t("playground.composer.placeholderNoAgent")} disabled={!agentId || !agentReady} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); event.currentTarget.form?.requestSubmit(); } }} /><button disabled={!agentId || busy || !agentReady} aria-label={t("playground.composer.send")}>{busy ? <LoaderCircle className="spin" size={18} /> : <Send size={18} />}</button></form><small>{t("playground.composer.disclaimer")}</small></div>
    </section>
  </div>;
}
