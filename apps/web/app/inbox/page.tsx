"use client";

import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { BadgeCheck, FlaskConical, Globe, Images, Inbox as InboxIcon, LoaderCircle, MessageCircle, Search, UserRound } from "lucide-react";
import { PageHead } from "@/components/ui";
import { AttachButton, MessageAttachments, PendingAttachment, RecordButton, useFileDrop, type GalleryImage } from "@/components/attachments";
import { MediaPanel } from "@/components/media-panel";
import { RichText } from "@/components/rich-text";
import { ListRowsSkeleton } from "@/components/skeleton";
import { useToast } from "@/components/toast";
import { api, apiUrl, messageFrom } from "@/lib/api";
import { formatTime, formatWhen, isNearBottom, isSameOpenThread } from "@/lib/datetime";
import { useLanguage, useT } from "@/lib/i18n";
import type { Agent, Attachment, Conversation, ConversationInbox } from "@/types";

const LIMIT = 30;
const POLL_MS = 8000;

export default function InboxPage() {
  const t = useT();
  const { lang } = useLanguage();
  const toast = useToast();
  const [agents, setAgents] = useState<Agent[]>([]);
  const [items, setItems] = useState<ConversationInbox[]>([]);
  const [selected, setSelected] = useState<Conversation | null>(null);
  const [agentId, setAgentId] = useState("");
  const [channel, setChannel] = useState("");
  const [tab, setTab] = useState<"all" | "unread" | "human" | "ai">("all");
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [offset, setOffset] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [busy, setBusy] = useState(false);
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const [mediaOpen, setMediaOpen] = useState(false);

  useEffect(() => { api<Agent[]>("/agents").then(setAgents).catch(() => {}); }, []);
  useEffect(() => { const id = setTimeout(() => setSearch(searchInput), 300); return () => clearTimeout(id); }, [searchInput]);

  const channelLabel = (value: string) => {
    if (value === "playground") return t("inbox.channelPlayground");
    if (value === "whatsapp") return t("inbox.channelWhatsapp");
    if (value === "whatsapp_cloud") return t("inbox.channelWhatsappCloud");
    if (value === "widget") return t("inbox.channelWidget");
    return value;
  };

  const channelIcon = (value: string) => {
    if (value === "whatsapp") return <MessageCircle size={10} />;
    if (value === "whatsapp_cloud") return <BadgeCheck size={10} />;
    if (value === "widget") return <Globe size={10} />;
    if (value === "playground") return <FlaskConical size={10} />;
    return <MessageCircle size={10} />;
  };

  const buildParams = useCallback((offsetValue: number) => {
    const params = new URLSearchParams();
    if (agentId) params.set("agent_id", agentId);
    if (channel) params.set("channel", channel);
    if (tab === "human" || tab === "ai") params.set("mode", tab);
    if (tab === "unread") params.set("unread", "1");
    if (search) params.set("search", search);
    params.set("limit", String(LIMIT));
    params.set("offset", String(offsetValue));
    return params.toString();
  }, [agentId, channel, tab, search]);

  const selectedIdRef = useRef<string | null>(null);
  const messagesRef = useRef<HTMLDivElement>(null);
  useEffect(() => { selectedIdRef.current = selected?.id ?? null; }, [selected]);
  const wasNearBottomRef = useRef(true);
  useEffect(() => {
    const el = messagesRef.current;
    if (el) { const handler = () => { wasNearBottomRef.current = isNearBottom(el); }; el.addEventListener("scroll", handler, { passive: true }); return () => el.removeEventListener("scroll", handler); }
  }, [selected?.id]);
  useEffect(() => {
    const el = messagesRef.current;
    if (!el) return;
    if (wasNearBottomRef.current) {
      const frame = requestAnimationFrame(() => { el.scrollTop = el.scrollHeight; });
      return () => cancelAnimationFrame(frame);
    }
  }, [selected?.id, selected?.messages?.at(-1)?.id]);

  const loadFirst = useCallback(async (opts?: { silent?: boolean }) => {
    if (!opts?.silent) setLoading(true);
    try {
      const rows = await api<ConversationInbox[]>(`/conversations/inbox?${buildParams(0)}`);
      setItems(rows); setOffset(rows.length); setHasMore(rows.length === LIMIT);
    } catch (err) {
      if (!opts?.silent) toast.error(messageFrom(err));
    } finally {
      if (!opts?.silent) setLoading(false);
    }
  }, [buildParams, toast]);

  const refreshSelected = useCallback(async () => {
    const id = selectedIdRef.current;
    if (!id) return;
    try {
      const conv = await api<Conversation>(`/conversations/${id}`);
      if (selectedIdRef.current !== id) return;
      setSelected((prev) => {
        if (isSameOpenThread(prev, conv)) return prev;
        setItems((rows) => rows.map((row) => (row.id === id ? { ...row, unread: false, unread_count: 0 } : row)));
        api(`/conversations/${id}/read`, { method: "POST" }).catch(() => {});
        return conv;
      });
    } catch {
      // Poll failures should not interrupt the open thread.
    }
  }, []);

  useEffect(() => { loadFirst(); }, [loadFirst]);

  // Live refresh of the first page and the open thread (skipped once the user scrolls into older pages).
  useEffect(() => {
    const id = setInterval(() => {
      if (offset <= LIMIT) {
        loadFirst({ silent: true });
        refreshSelected();
      }
    }, POLL_MS);
    return () => clearInterval(id);
  }, [loadFirst, refreshSelected, offset]);

  async function loadMore() {
    if (loadingMore || !hasMore) return;
    setLoadingMore(true);
    try {
      const rows = await api<ConversationInbox[]>(`/conversations/inbox?${buildParams(offset)}`);
      setItems((prev) => [...prev, ...rows]); setOffset((o) => o + rows.length); setHasMore(rows.length === LIMIT);
    } catch (err) { toast.error(messageFrom(err)); } finally { setLoadingMore(false); }
  }

  function onScroll(event: React.UIEvent<HTMLElement>) {
    const el = event.currentTarget;
    if (el.scrollHeight - el.scrollTop - el.clientHeight < 80) loadMore();
  }

  async function choose(id: string) {
    selectedIdRef.current = id;
    setSelected(await api<Conversation>(`/conversations/${id}`));
    setItems((rows) => rows.map((row) => (row.id === id ? { ...row, unread: false, unread_count: 0 } : row)));
    api(`/conversations/${id}/read`, { method: "POST" }).catch(() => {});
  }

  async function toggleMode(next: "ai" | "human") {
    if (!selected) return;
    setSelected(await api<Conversation>(`/conversations/${selected.id}/mode`, { method: "PATCH", body: JSON.stringify({ mode: next }) }));
    loadFirst({ silent: true });
  }

  const composerRef = useRef<HTMLInputElement>(null);
  async function reply(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected) return;
    if (pendingFile) {
      const file = pendingFile;
      setPendingFile(null);
      await sendAttachment(file);
      return;
    }
    const form = event.currentTarget;
    const data = new FormData(form);
    setBusy(true);
    try {
      setSelected(await api<Conversation>(`/conversations/${selected.id}/reply`, { method: "POST", body: JSON.stringify({ content: data.get("content") }) }));
      form.reset();
      loadFirst({ silent: true });
    } catch (err) { toast.error(messageFrom(err)); } finally { setBusy(false); composerRef.current?.focus(); }
  }

  async function sendAttachment(file?: File) {
    if (!file || !selected || selected.mode !== "human" || busy) return;
    setBusy(true);
    const caption = (composerRef.current?.value || "").trim();
    try {
      const data = new FormData();
      data.append("file", file);
      if (caption) data.append("caption", caption);
      setSelected(await api<Conversation>(`/conversations/${selected.id}/reply-media`, { method: "POST", body: data }));
      if (composerRef.current) composerRef.current.value = "";
      loadFirst({ silent: true });
    } catch (err) { toast.error(messageFrom(err)); } finally { setBusy(false); composerRef.current?.focus(); }
  }
  const { dropProps, overlay } = useFileDrop(setPendingFile, { enabled: Boolean(selected) && selected?.mode === "human" && !busy, label: t("chat.dropToSend") });

  const selectedId = selected?.id;
  const attachmentUrl = useCallback(
    (attachment: Attachment) => apiUrl(`/conversations/${selectedId}/attachments/${attachment.id}`),
    [selectedId],
  );
  const gallery: GalleryImage[] = useMemo(
    () => (selected?.messages ?? []).flatMap((message) =>
      (message.attachments ?? []).filter((a) => a.kind === "image").map((a) => ({ id: a.id, url: attachmentUrl(a), name: a.filename }))
    ),
    [selected, attachmentUrl],
  );

  return <div className="page">
    <PageHead eyebrow={t("inbox.eyebrow")} title={t("inbox.title")} description={t("inbox.description")} />

    <div className="toolbar filters">
      <div className="filter-select"><span>{t("inbox.filterAgent")}</span><select value={agentId} onChange={(e) => setAgentId(e.target.value)}><option value="">{t("inbox.allAgents")}</option>{agents.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}</select></div>
      <div className="filter-select"><span>{t("inbox.filterChannel")}</span><select value={channel} onChange={(e) => setChannel(e.target.value)}><option value="">{t("inbox.allChannels")}</option><option value="playground">{t("inbox.channelPlayground")}</option><option value="whatsapp">{t("inbox.channelWhatsapp")}</option><option value="whatsapp_cloud">{t("inbox.channelWhatsappCloud")}</option><option value="widget">{t("inbox.channelWidget")}</option></select></div>
    </div>

    <div className="inbox-layout">
      <aside className="inbox-list" onScroll={onScroll}>
        <div className="inbox-search"><Search size={16} /><input value={searchInput} onChange={(e) => setSearchInput(e.target.value)} placeholder={t("inbox.searchPlaceholder")} /></div>
        <div className="inbox-tabs">
          <button className={tab === "all" ? "active" : ""} onClick={() => setTab("all")}>{t("inbox.tabAll")}</button>
          <button className={tab === "unread" ? "active" : ""} onClick={() => setTab("unread")}>{t("inbox.tabUnread")}</button>
          <button className={tab === "human" ? "active" : ""} onClick={() => setTab("human")}>{t("inbox.statusHuman")}</button>
          <button className={tab === "ai" ? "active" : ""} onClick={() => setTab("ai")}>{t("inbox.statusAi")}</button>
        </div>
        {loading ? <ListRowsSkeleton rows={7} />
          : items.length ? <>
            {items.map((item) => (
              <button key={item.id} className={`inbox-row ${selected?.id === item.id ? "active" : ""} ${item.unread ? "unread" : ""}`} onClick={() => choose(item.id)}>
                <span className="inbox-avatar">
                  <span className="entity-avatar tiny"><UserRound size={15} /></span>
                  <span className={`channel-badge ${item.channel}`} title={channelLabel(item.channel)}>{channelIcon(item.channel)}</span>
                </span>
                <span className="inbox-row-body">
                  <span className="inbox-row-top"><strong>{item.contact_name || item.title}</strong><time>{formatWhen(item.updated_at, lang)}</time></span>
                  <small className="inbox-row-preview">{item.preview || t("inbox.noMessages")}</small>
                  <small className="inbox-row-meta">{item.agent_name} · {channelLabel(item.channel)} <span className={`mini-badge ${item.mode}`}>{item.mode === "human" ? t("inbox.modeHuman") : t("inbox.modeAi")}</span></small>
                </span>
                {item.unread_count > 0 && selected?.id !== item.id && <span className="inbox-unread-count" aria-label={t("inbox.unreadCount", { count: item.unread_count })}>{item.unread_count > 99 ? "99+" : item.unread_count}</span>}
              </button>
            ))}
            {loadingMore && <div className="no-conversations"><LoaderCircle className="spin" size={15} /></div>}
          </> : <div className="no-conversations">{t("inbox.empty")}</div>}
      </aside>

      <section className="inbox-thread drop-target" {...dropProps}>
        {overlay}
        {!selected ? <div className="empty-state"><div className="empty-icon"><InboxIcon /></div><h3>{t("inbox.empty")}</h3><p>{t("inbox.selectPrompt")}</p></div>
          : <>
            <header>
              <div><strong>{selected.contact_name || selected.title}</strong><small>{channelLabel(selected.channel)}</small></div>
              <div className="thread-actions">
                <button className="icon-button" onClick={() => setMediaOpen(true)} title={t("chat.sharedContent")} aria-label={t("chat.sharedContent")}><Images size={16} /></button>
                <button className={`mode-toggle ${selected.mode}`} onClick={() => toggleMode(selected.mode === "ai" ? "human" : "ai")}>{selected.mode === "ai" ? t("inbox.takeControl") : t("inbox.returnToAi")}</button>
              </div>
            </header>
            <div className="inbox-messages" ref={messagesRef}>
              {selected.messages?.map((message, index) => {
                const prev = index > 0 ? selected.messages![index - 1] : null;
                const grouped = Boolean(prev && prev.role === message.role && prev.sender_name === message.sender_name);
                const stamp = formatTime(message.created_at, lang);
                const hasAudio = message.attachments?.some((a) => a.kind === "audio");
                return (
                  <div key={message.id} className={`inbox-message ${message.role}${grouped ? " grouped" : ""}`}>
                    {!grouped && <small>{message.sender_name || (message.role === "assistant" ? t("inbox.senderAgent") : t("inbox.senderVisitor"))}</small>}
                    <MessageAttachments attachments={message.attachments} urlFor={attachmentUrl} gallery={gallery} stamp={stamp} />
                    {message.content ? <p><RichText text={message.content} /><time className="msg-time">{stamp}</time></p>
                      : !hasAudio && message.attachments?.length ? <time className="msg-time bare">{stamp}</time> : null}
                  </div>
                );
              })}
            </div>
            {pendingFile && <PendingAttachment file={pendingFile} onCancel={() => setPendingFile(null)} />}
            <form className="inbox-composer" onSubmit={reply}>
              <AttachButton onFile={setPendingFile} disabled={selected.mode !== "human" || busy} title={t("chat.attachFile")} />
              <RecordButton onRecorded={sendAttachment} onError={() => toast.error(t("chat.micDenied"))} disabled={selected.mode !== "human" || busy} title={t("chat.recordAudio")} titleStop={t("chat.stopRecording")} />
              <input ref={composerRef} name="content" placeholder={selected.mode === "human" ? t("inbox.composerHuman") : t("inbox.composerLocked")} disabled={selected.mode !== "human"} required={!pendingFile} />
              <button disabled={selected.mode !== "human" || busy}>{t("inbox.send")}</button>
            </form>
            <MediaPanel open={mediaOpen} onClose={() => setMediaOpen(false)} messages={selected.messages ?? []} urlFor={attachmentUrl} />
          </>}
      </section>
    </div>
  </div>;
}
