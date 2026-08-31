"use client";

import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "next/navigation";
import { BadgeCheck, Bot, Building2, CheckCircle2, Clock, Contact as ContactIcon, FileText, FlaskConical, Globe, Images, Inbox, LoaderCircle, LogOut, MessageCircle, MessageSquareText, Reply, Search, Send, ShieldCheck, SmilePlus, UserRound, X } from "lucide-react";
import { ContactsView } from "./contacts";
import { TemplatePicker, TemplatesView } from "./templates";
import { AttachButton, MessageAttachments, PendingAttachment, RecordButton, useFileDrop, type GalleryImage } from "@/components/attachments";
import { LanguageSwitcher } from "@/components/language-switcher";
import { MediaPanel } from "@/components/media-panel";
import { RichText } from "@/components/rich-text";
import { QuotedSnippet, ReactionBadge, ReactionPicker } from "@/components/message-gestures";
import { DeliveryTicks } from "@/components/delivery-ticks";
import { useToast } from "@/components/toast";
import { Alert, EmptyState } from "@/components/ui";
import { api, ApiError, apiUrl, messageFrom } from "@/lib/api";
import { formatTime, formatWhen, isNearBottom, isSameOpenThread } from "@/lib/datetime";
import { useLanguage, useT } from "@/lib/i18n";
import type { Attachment, Conversation, Message, PortalChannel, PortalPublic } from "@/types";

const POLL_MS = 8000;

function chime() {
  try {
    const ctx = new (window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext)();
    const play = (freq: number, at: number) => {
      const osc = ctx.createOscillator(); const gain = ctx.createGain();
      osc.type = "sine"; osc.frequency.value = freq;
      gain.gain.setValueAtTime(0.0001, ctx.currentTime + at);
      gain.gain.exponentialRampToValueAtTime(0.18, ctx.currentTime + at + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + at + 0.28);
      osc.connect(gain).connect(ctx.destination);
      osc.start(ctx.currentTime + at); osc.stop(ctx.currentTime + at + 0.3);
    };
    play(880, 0); play(1175, 0.16);
    setTimeout(() => ctx.close().catch(() => {}), 800);
  } catch { /* no audio available */ }
}
const LIMIT = 30;

type Session = { client_id: string; client_name: string; portal_slug: string; agency_name: string; user_id?: string | null; user_name?: string | null };
type Member = { id: string; name: string; email: string };
type InboxSummary = { open: number; resolved: number; human: number; ai: number; unread: number; mine: number; unassigned: number };

export default function PortalPage() {
  const t = useT();
  const { slug } = useParams<{ slug: string }>();
  const [portal, setPortal] = useState<PortalPublic | null>(null);
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  useEffect(() => { Promise.all([api<PortalPublic>(`/portal/${slug}`), api<Session>(`/portal/${slug}/me`).catch((err) => { if (err instanceof ApiError && err.status === 401) return null; throw err; })]).then(([info, me]) => { setPortal(info); setSession(me); }).catch((err) => setError(messageFrom(err))).finally(() => setLoading(false)); }, [slug]);
  async function login(event: FormEvent<HTMLFormElement>) { event.preventDefault(); setError(""); const data = new FormData(event.currentTarget); try { setSession(await api<Session>(`/portal/${slug}/login`, { method: "POST", body: JSON.stringify({ email: data.get("email"), password: data.get("password") }) })); } catch (err) { setError(messageFrom(err)); } }
  async function logout() { await api(`/portal/${slug}/logout`, { method: "POST" }); setSession(null); }
  if (loading) return <div className="portal-loader"><LoaderCircle className="spin" /> {t("portal.loader.loading")}</div>;
  if (!portal) return <div className="portal-loader">{error || t("portal.loader.unavailable")}</div>;
  if (!session) return <main className="access-page portal-access" style={{ "--portal-color": portal.agency_brand_color } as React.CSSProperties}><header className="access-topbar"><div className="access-brand portal-access-brand">{portal.agency_logo_url ? <img src={`${portal.agency_logo_url}`} alt={portal.agency_name} /> : <span>{portal.agency_name.slice(0, 1)}</span>}<strong>{portal.agency_name}</strong></div><small>{t("portal.access.secureBadge")}</small></header><div className="access-layout"><section className="access-intro"><span className="access-eyebrow">{t("portal.access.eyebrow")}</span><h1>{portal.portal_title}</h1><p>{t("portal.access.intro")}</p><div className="access-preview portal-preview" aria-hidden="true"><header><div><span className="preview-logo"><Inbox size={16} /></span><strong>{t("portal.access.preview.inbox")}</strong></div><small>{t("portal.access.preview.conversationsCount")}</small></header><div className="portal-preview-thread"><div className="active"><span className="preview-icon"><UserRound size={16} /></span><p><strong>{t("portal.access.preview.newInquiry")}</strong><small>{t("portal.access.preview.newInquiryMeta")}</small></p><em>2</em></div><div><span className="preview-icon"><MessageSquareText size={16} /></span><p><strong>{t("portal.access.preview.salesFollowUp")}</strong><small>{t("portal.access.preview.salesFollowUpMeta")}</small></p></div><div><span className="preview-icon"><Building2 size={16} /></span><p><strong>{t("portal.access.preview.servicesInfo")}</strong><small>{t("portal.access.preview.servicesInfoMeta")}</small></p></div></div><footer><span><Bot size={15} /> {t("portal.access.preview.agentReplying")}</span><strong>{t("portal.access.preview.takeControl")}</strong></footer></div></section><section className="access-form-wrap"><form className="access-card access-form" onSubmit={login}><span className="portal-client-avatar">{portal.client_name.slice(0, 2).toUpperCase()}</span><span className="access-card-label"><ShieldCheck size={15} /> {t("portal.access.form.cardLabel")}</span><h2>{t("portal.access.form.welcome", { name: portal.client_name })}</h2><p>{t("portal.access.form.subtitle")}</p><label>{t("portal.access.form.emailLabel")}<input name="email" type="email" required autoFocus placeholder={t("portal.access.form.emailPlaceholder")} /></label><label>{t("portal.access.form.passwordLabel")}<input name="password" type="password" required placeholder={t("portal.access.form.passwordPlaceholder")} /></label>{error && <Alert>{error}</Alert>}<button className="button primary full">{t("portal.access.form.submit")}</button><small className="access-security"><ShieldCheck size={14} /> {t("portal.access.form.security", { name: portal.agency_name })}</small></form></section></div></main>;
  return <PortalInbox slug={slug} portal={portal} session={session} logout={logout} />;
}

function PortalInbox({ slug, portal, session, logout }: { slug: string; portal: PortalPublic; session: Session; logout: () => void }) {
  const t = useT();
  const { lang } = useLanguage();
  const [items, setItems] = useState<Conversation[]>([]);
  const [selected, setSelected] = useState<Conversation | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const [quoting, setQuoting] = useState<Message | null>(null);
  const [reactingTo, setReactingTo] = useState<string | null>(null);
  const [tab, setTab] = useState<"all" | "unread" | "mine" | "ai">("all");
  const [members, setMembers] = useState<Member[]>([]);
  useEffect(() => { api<Member[]>(`/portal/${slug}/members`).then(setMembers).catch(() => {}); }, [slug]);
  const toast = useToast();
  // Conversations handed to me: the first poll only learns what is mine,
  // every later one announces what is new, so a transfer is felt at once.
  const mineKnownRef = useRef<Set<string> | null>(null);
  const announceAssignments = useCallback(async () => {
    if (!session.user_id) return;
    const mine = await api<Conversation[]>(`/portal/${slug}/conversations?status=open&assignee=me&limit=100`);
    const known = mineKnownRef.current;
    const next = new Set(mine.map((row) => row.id));
    if (known) {
      const fresh = mine.filter((row) => !known.has(row.id));
      if (fresh.length) {
        chime();
        for (const row of fresh) {
          const text = t("portal.inbox.assignment.received", { title: row.title });
          toast.info(text);
          if (typeof Notification !== "undefined" && Notification.permission === "granted") {
            try { new Notification(portal.portal_title, { body: text }); } catch { /* blocked */ }
          }
        }
      }
    }
    mineKnownRef.current = next;
  }, [slug, session.user_id, t, toast, portal.portal_title]);
  useEffect(() => {
    if (typeof Notification !== "undefined" && Notification.permission === "default") {
      Notification.requestPermission().catch(() => {});
    }
  }, []);
  const [status, setStatus] = useState<"open" | "resolved">("open");
  const [summary, setSummary] = useState<InboxSummary | null>(null);
  const [view, setView] = useState<"inbox" | "contacts" | "templates">("inbox");
  const [channels, setChannels] = useState<PortalChannel[]>([]);
  useEffect(() => { api<PortalChannel[]>(`/portal/${slug}/channels`).then(setChannels).catch(() => {}); }, [slug]);
  const templatesSupported = channels.some((c) => c.channel === "whatsapp_cloud" && c.supports_templates);
  const [templateOpen, setTemplateOpen] = useState(false);
  async function openFromContact(conversation: Conversation) {
    // Fetch first, then switch everything in one render: the selection is in
    // place before the list reloads for the conversation's inbox.
    const detail = await api<Conversation>(`/portal/${slug}/conversations/${conversation.id}`);
    setSelected(detail);
    setStatus(conversation.status === "resolved" ? "resolved" : "open");
    setTab("all");
    setView("inbox");
  }
  function switchStatus(next: "open" | "resolved") {
    if (next === status) return;
    setStatus(next); setTab("all");
    // Clearing the selection also clears the ref, through the effect that
    // keeps them in sync, before the list reloads for the new inbox.
    setSelected(null);
  }
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [offset, setOffset] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [mediaOpen, setMediaOpen] = useState(false);
  const selectedIdRef = useRef<string | null>(null);

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
  // Search is sent to the server after a short pause, so the list, the tabs
  // and paging all agree on the same filter.
  useEffect(() => {
    const id = setTimeout(() => setQuery(search.trim()), 300);
    return () => clearTimeout(id);
  }, [search]);
  const buildParams = useCallback((offsetValue: number) => {
    const params = new URLSearchParams();
    params.set("status", status);
    if (tab === "ai") params.set("mode", "ai");
    if (tab === "mine") params.set("assignee", "me");
    if (tab === "unread") params.set("unread", "1");
    if (query) params.set("search", query);
    params.set("limit", String(LIMIT));
    params.set("offset", String(offsetValue));
    return params.toString();
  }, [tab, status, query]);
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

  const markRead = useCallback((id: string) => {
    setItems((rows) => rows.map((row) => (row.id === id ? { ...row, unread: false, unread_count: 0 } : row)));
    setSummary((prev) => (prev && prev.unread > 0 ? { ...prev, unread: prev.unread - 1 } : prev));
    api(`/portal/${slug}/conversations/${id}/read`, { method: "POST" }).catch(() => {});
  }, [slug]);

  const refresh = useCallback(async () => {
    api<InboxSummary>(`/portal/${slug}/conversations/summary`).then(setSummary).catch(() => {});
    announceAssignments().catch(() => {});
    const rows = await api<Conversation[]>(`/portal/${slug}/conversations?${buildParams(0)}`);
    setItems(rows); setOffset(rows.length); setHasMore(rows.length === LIMIT);
    const openId = selectedIdRef.current ?? rows[0]?.id;
    if (!openId) return;
    const conv = await api<Conversation>(`/portal/${slug}/conversations/${openId}`);
    if (selectedIdRef.current && selectedIdRef.current !== openId) return;
    if (!selectedIdRef.current) { selectedIdRef.current = openId; markRead(openId); }
    setSelected((prev) => {
      if (isSameOpenThread(prev, conv)) return prev;
      // New visitor messages arrived while this thread is on screen: they are read.
      if (prev && rows.find((row) => row.id === openId)?.unread) markRead(openId);
      return conv;
    });
  }, [slug, buildParams, markRead, announceAssignments]);

  useEffect(() => { refresh().catch((err) => setError(messageFrom(err))); }, [refresh]);
  useEffect(() => {
    const id = setInterval(() => { if (offset <= LIMIT) refresh().catch(() => {}); }, POLL_MS);
    return () => clearInterval(id);
  }, [refresh, offset]);

  async function loadMore() {
    if (!hasMore || loadingMore) return;
    setLoadingMore(true);
    try {
      const rows = await api<Conversation[]>(`/portal/${slug}/conversations?${buildParams(offset)}`);
      setItems((prev) => [...prev, ...rows]); setOffset((o) => o + rows.length); setHasMore(rows.length === LIMIT);
    } catch (err) { setError(messageFrom(err)); } finally { setLoadingMore(false); }
  }
  function onListScroll(event: React.UIEvent<HTMLElement>) {
    const el = event.currentTarget;
    if (el.scrollHeight - el.scrollTop - el.clientHeight < 80) loadMore();
  }

  async function choose(item: Conversation) {
    selectedIdRef.current = item.id;
    setQuoting(null);
    setReactingTo(null);
    markRead(item.id);
    setSelected(await api<Conversation>(`/portal/${slug}/conversations/${item.id}`));
  }
  async function sendReaction(message: Message, emoji: string) {
    if (!selected) return;
    setReactingTo(null);
    setError("");
    try {
      setSelected(await api<Conversation>(`/portal/${slug}/conversations/${selected.id}/messages/${message.id}/reaction`, { method: "POST", body: JSON.stringify({ emoji }) }));
    } catch (err) { setError(messageFrom(err)); }
  }
  async function setMode(mode: "ai" | "human") { if (!selected) return; setSelected(await api<Conversation>(`/portal/${slug}/conversations/${selected.id}/mode`, { method: "PATCH", body: JSON.stringify({ mode }) })); await refresh(); }
  async function setConversationStatus(next: "open" | "resolved") {
    if (!selected) return;
    setSelected(await api<Conversation>(`/portal/${slug}/conversations/${selected.id}/status`, { method: "PATCH", body: JSON.stringify({ status: next }) }));
    await refresh();
  }
  async function assignTo(assigneeId: string) {
    if (!selected) return;
    setSelected(await api<Conversation>(`/portal/${slug}/conversations/${selected.id}/assignment`, { method: "POST", body: JSON.stringify({ assignee_id: assigneeId }) }));
    await refresh();
  }
  async function replyWithTemplate(payload: { name: string; language: string; variables: string[] }) {
    if (!selected) return;
    setSelected(await api<Conversation>(`/portal/${slug}/conversations/${selected.id}/reply-template`, { method: "POST", body: JSON.stringify(payload) }));
    await refresh();
  }
  const memberLabel = (member: Member) => (member.id === session.user_id ? t("portal.inbox.assignment.me", { name: member.name }) : member.name);
  const isResolved = selected?.status === "resolved";
  const windowClosed = Boolean(selected) && selected?.channel === "whatsapp_cloud" && selected?.reply_window_open === false;
  const canReply = Boolean(selected) && selected?.mode === "human" && !isResolved && !windowClosed;
  const activityText = (message: Message) => {
    const actor = message.sender_name || t("portal.inbox.activity.someone");
    switch (message.activity?.event) {
      case "resolved": return t("portal.inbox.activity.resolved", { actor });
      case "reopened": return t("portal.inbox.activity.reopened", { actor });
      case "reopened_by_contact": return t("portal.inbox.activity.reopened_by_contact");
      case "taken_over": return t("portal.inbox.activity.taken_over", { actor });
      case "returned_to_ai": return t("portal.inbox.activity.returned_to_ai", { actor });
      case "auto_resolved": return t("portal.inbox.activity.auto_resolved", { hours: String(message.activity?.hours ?? "") });
      case "self_assigned": return t("portal.inbox.activity.self_assigned", { actor });
      case "assigned": return t("portal.inbox.activity.assigned", { actor, assignee: String(message.activity?.assignee ?? "") });
      case "transferred": return t("portal.inbox.activity.transferred", { actor, assignee: String(message.activity?.assignee ?? "") });
      case "unassigned": return t("portal.inbox.activity.unassigned", { actor });
      default: return message.content;
    }
  };
  async function reply(event: FormEvent<HTMLFormElement>) { event.preventDefault(); if (!selected) return; if (pendingFile) { const file = pendingFile; setPendingFile(null); await sendAttachment(file); return; } const form = event.currentTarget; const data = new FormData(form); setBusy(true); setError(""); try { setSelected(await api<Conversation>(`/portal/${slug}/conversations/${selected.id}/reply`, { method: "POST", body: JSON.stringify({ content: data.get("content"), quoted_message_id: quoting?.id ?? null }) })); form.reset(); setQuoting(null); await refresh(); } catch (err) { setError(messageFrom(err)); } finally { setBusy(false); } }
  const replyInputRef = useRef<HTMLInputElement>(null);
  async function sendAttachment(file?: File) {
    if (!file || !selected || !canReply || busy) return;
    setBusy(true); setError("");
    const caption = (replyInputRef.current?.value || "").trim();
    try {
      const data = new FormData();
      data.append("file", file);
      if (caption) data.append("caption", caption);
      setSelected(await api<Conversation>(`/portal/${slug}/conversations/${selected.id}/reply-media`, { method: "POST", body: data }));
      if (replyInputRef.current) replyInputRef.current.value = "";
      await refresh();
    } catch (err) { setError(messageFrom(err)); } finally { setBusy(false); }
  }
  const { dropProps, overlay } = useFileDrop(setPendingFile, { enabled: canReply && !busy, label: t("chat.dropToSend") });

  const selectedId = selected?.id;
  const attachmentUrl = useCallback(
    (attachment: Attachment) => apiUrl(`/portal/${slug}/conversations/${selectedId}/attachments/${attachment.id}`),
    [slug, selectedId],
  );
  const gallery: GalleryImage[] = useMemo(
    () => (selected?.messages ?? []).flatMap((message) =>
      (message.attachments ?? []).filter((a) => a.kind === "image").map((a) => ({ id: a.id, url: attachmentUrl(a), name: a.filename }))
    ),
    [selected, attachmentUrl],
  );
  return <main className="portal-app" style={{ "--portal-color": portal.agency_brand_color } as React.CSSProperties}><aside className="portal-nav"><div className="portal-brand">{portal.client_logo_url || portal.agency_logo_url ? <img src={`${portal.client_logo_url || portal.agency_logo_url}`} alt="Logo" /> : <span>{portal.client_name.slice(0, 1)}</span>}<strong>{portal.client_name}</strong></div><nav><a className={view === "inbox" ? "active" : ""} onClick={() => setView("inbox")}><Inbox size={18} /> {t("portal.inbox.nav.inbox")}{summary && summary.unread > 0 && view !== "inbox" && <em className="nav-count">{summary.unread}</em>}</a><a className={view === "contacts" ? "active" : ""} onClick={() => setView("contacts")}><ContactIcon size={18} /> {t("portal.inbox.nav.contacts")}</a><a className={view === "templates" ? "active" : ""} onClick={() => setView("templates")}><FileText size={18} /> {t("portal.inbox.nav.templates")}</a><a className="disabled"><Bot size={18} /> {t("portal.inbox.nav.agents")}</a></nav><LanguageSwitcher /><button onClick={logout}><LogOut size={17} /> {t("portal.inbox.nav.logout")}</button></aside><section className="portal-main"><header><div><small>{t("portal.inbox.header.eyebrow")}</small><h1>{view === "contacts" ? t("portal.inbox.nav.contacts") : view === "templates" ? t("portal.inbox.nav.templates") : portal.portal_title}</h1></div>{view === "inbox" && <span>{t("portal.inbox.header.conversationsCount", { count: items.length })}</span>}</header>{view === "templates" ? <TemplatesView slug={slug} supported={templatesSupported} /> : view === "contacts" ? <ContactsView slug={slug} channels={channels} openConversation={openFromContact} /> : <div className="portal-inbox"><aside onScroll={onListScroll}>
      <div className="inbox-search"><Search size={16} /><input value={search} onChange={(e) => setSearch(e.target.value)} placeholder={t("inbox.searchPlaceholder")} /></div>
      <div className="segmented" role="tablist" aria-label={t("portal.inbox.status.open") + " / " + t("portal.inbox.status.resolved")}>
        <button role="tab" aria-selected={status === "open"} className={status === "open" ? "active" : ""} onClick={() => switchStatus("open")}><Inbox size={14} /> {t("portal.inbox.status.open")}</button>
        <button role="tab" aria-selected={status === "resolved"} className={status === "resolved" ? "active" : ""} onClick={() => switchStatus("resolved")}><CheckCircle2 size={14} /> {t("portal.inbox.status.resolved")}</button>
      </div>
      {status === "open" && <div className="inbox-tabs">
        <button className={tab === "all" ? "active" : ""} onClick={() => setTab("all")}>{t("portal.inbox.folders.all")}</button>
        <button className={tab === "unread" ? "active" : ""} onClick={() => setTab("unread")}>{t("portal.inbox.folders.unread")}{summary && summary.unread > 0 && <em>{summary.unread > 99 ? "99+" : summary.unread}</em>}</button>
        <button className={tab === "mine" ? "active" : ""} onClick={() => setTab("mine")}>{t("portal.inbox.folders.mine")}{summary && summary.mine > 0 && <em className="soft">{summary.mine}</em>}</button>
        <button className={tab === "ai" ? "active" : ""} onClick={() => setTab("ai")}>{t("portal.inbox.folders.ai")}</button>
      </div>}
      {items.map((item) => <button key={item.id} onClick={() => choose(item)} className={`${selected?.id === item.id ? "active" : ""}${item.unread && selected?.id !== item.id ? " unread" : ""}`}><span className="entity-avatar tiny"><UserRound size={15} /></span><span><span className="portal-inbox-row-top"><strong>{item.title}</strong>{item.unread && selected?.id !== item.id ? <span className="inbox-unread-count" aria-label={t("inbox.unreadCount", { count: item.unread_count ?? 0 })}>{(item.unread_count ?? 0) > 99 ? "99+" : item.unread_count}</span> : <time>{formatWhen(item.updated_at, lang)}</time>}</span><small className="portal-inbox-preview">{item.preview || t("portal.inbox.list.noMessages")}</small><small className="inbox-row-meta"><span className={`channel-dot ${item.channel}`}>{channelIcon(item.channel)}</span> {channelLabel(item.channel)} <span className={`mini-badge ${item.mode}`}>{item.mode === "human" ? (item.assignee_name || t("portal.inbox.list.humanSupport")) : t("portal.inbox.list.aiAgent")}</span></small></span></button>)}
      {!items.length && <div className="no-conversations">{t("inbox.empty")}</div>}
      {loadingMore && <div className="no-conversations"><LoaderCircle className="spin" size={16} /></div>}
    </aside><section className="drop-target" {...dropProps}>{overlay}{!selected && <EmptyState icon={<Inbox />} title={t("portal.inbox.empty.title")} description={t("portal.inbox.empty.description")} />}{selected && <><header><div><strong>{selected.title}</strong><small className="portal-channel-line">{channelIcon(selected.channel)} {channelLabel(selected.channel)} <span className={`mini-badge ${selected.mode}`}>{selected.mode === "human" ? t("portal.inbox.list.humanSupport") : t("portal.inbox.list.aiAgent")}</span>{isResolved && <span className="mini-badge resolved"><CheckCircle2 size={11} /> {t("portal.inbox.conversation.resolvedBadge")}</span>}{selected.channel === "whatsapp_cloud" && !isResolved && !selected.reply_window_open && <span className="window-pill closed"><Clock size={11} /> {selected.reply_window_until ? t("portal.inbox.window.closed") : t("portal.inbox.window.neverWrote")}</span>}</small></div><div className="thread-actions">{!isResolved && selected.mode === "human" && <label className="assignee-picker"><span>{t("portal.inbox.assignment.label")}</span><select aria-label={t("portal.inbox.assignment.label")} title={t("portal.inbox.assignment.label")} value={selected.assignee_id ?? ""} onChange={(e) => e.target.value && assignTo(e.target.value)}>{!selected.assignee_id && <option value="">{t("portal.inbox.assignment.pick")}</option>}{members.map((member) => <option key={member.id} value={member.id}>{memberLabel(member)}</option>)}</select></label>}<button className="icon-button" onClick={() => setMediaOpen(true)} title={t("chat.sharedContent")} aria-label={t("chat.sharedContent")}><Images size={16} /></button>{!isResolved && <><button className={`mode-toggle ${selected.mode}`} onClick={() => setMode(selected.mode === "ai" ? "human" : "ai")}>{selected.mode === "ai" ? t("portal.inbox.conversation.takeControl") : t("portal.inbox.conversation.returnToAi")}</button><button className="status-toggle open" onClick={() => setConversationStatus("resolved")}><CheckCircle2 size={15} /> {t("portal.inbox.conversation.resolve")}</button></>}</div></header><div className="portal-messages" ref={messagesRef}>{selected.messages?.map((message, index) => {
              if (message.kind === "activity") {
                return <div key={message.id} className="activity-line"><span>{activityText(message)}</span><time>{formatTime(message.created_at, lang)}</time></div>;
              }
              const prev = index > 0 ? selected.messages![index - 1] : null;
              const grouped = Boolean(prev && prev.kind !== "activity" && prev.role === message.role && prev.sender_name === message.sender_name);
              const stamp = formatTime(message.created_at, lang);
              const hasAudio = message.attachments?.some((a) => a.kind === "audio");
              const mine = message.role === "assistant";
              return <article key={message.id} className={`${message.role}${mine ? " mine" : ""}${mine && message.sender_type === "ai" ? " ai" : ""}${grouped ? " grouped" : ""}`}>
                {!grouped && <small>{message.sender_name || (message.role === "assistant" ? t("portal.inbox.conversation.agent") : t("portal.inbox.conversation.visitor"))}</small>}
                {canReply && <span className="bubble-actions">
                  {message.role === "user" && <button type="button" title={t("portal.inbox.conversation.react")} aria-label={t("portal.inbox.conversation.react")} onClick={() => setReactingTo(reactingTo === message.id ? null : message.id)}><SmilePlus size={14} /></button>}
                  <button type="button" title={t("portal.inbox.conversation.reply")} aria-label={t("portal.inbox.conversation.reply")} onClick={() => { setQuoting(message); replyInputRef.current?.focus(); }}><Reply size={14} /></button>
                </span>}
                <MessageAttachments attachments={message.attachments} urlFor={attachmentUrl} gallery={gallery} stamp={stamp} />
                {message.content && <p><QuotedSnippet messages={selected.messages ?? []} quotedId={message.quoted_message_id} /><RichText text={message.content} /><time className="msg-time">{stamp}{mine && selected.channel === "whatsapp_cloud" && <DeliveryTicks status={message.delivery_status} error={message.delivery_error} />}</time></p>}
                <ReactionBadge emoji={message.reaction} />
                <ReactionBadge emoji={message.incoming_reaction} incoming />
                {!message.content && !hasAudio && message.attachments?.length ? <time className="msg-time bare">{stamp}</time> : null}
                {reactingTo === message.id && <ReactionPicker current={message.reaction} removeLabel={t("portal.inbox.conversation.removeReaction")} onPick={(emoji) => sendReaction(message, emoji)} />}
              </article>;
            })}</div>{error && <Alert>{error}</Alert>}{pendingFile && <PendingAttachment file={pendingFile} onCancel={() => setPendingFile(null)} />}{quoting && <div className="composer-quote"><Reply size={14} /><span><strong>{t("portal.inbox.conversation.replyingTo", { name: quoting.sender_name || (quoting.role === "assistant" ? t("portal.inbox.conversation.agent") : t("portal.inbox.conversation.visitor")) })}</strong><small>{(quoting.content || "").slice(0, 140)}</small></span><button type="button" onClick={() => setQuoting(null)} aria-label={t("portal.inbox.conversation.cancelReply")} title={t("portal.inbox.conversation.cancelReply")}><X size={14} /></button></div>}{windowClosed && !isResolved && selected.mode === "human" ? <div className="portal-composer window-closed"><div><strong>{selected.reply_window_until ? t("portal.inbox.window.closed") : t("portal.inbox.window.neverWrote")}</strong><small>{t("portal.inbox.window.closedHint")}</small></div><button type="button" className="button primary" onClick={() => setTemplateOpen(true)} disabled={!templatesSupported}><FileText size={16} /> {t("portal.inbox.window.sendTemplate")}</button></div> : <form onSubmit={reply} className="portal-composer"><AttachButton onFile={setPendingFile} disabled={!canReply || busy} title={t("chat.attachFile")} /><RecordButton onRecorded={sendAttachment} onError={() => setError(t("chat.micDenied"))} disabled={!canReply || busy} title={t("chat.recordAudio")} titleStop={t("chat.stopRecording")} /><input ref={replyInputRef} name="content" required={!pendingFile} disabled={!canReply || busy} placeholder={isResolved ? t("portal.inbox.conversation.resolvedLocked") : selected.mode === "human" ? t("portal.inbox.conversation.replyPlaceholder") : t("portal.inbox.conversation.takeControlToReply")} /><button disabled={!canReply || busy}>{busy ? <LoaderCircle className="spin" size={18} /> : <Send size={18} />}</button></form>}<MediaPanel open={mediaOpen} onClose={() => setMediaOpen(false)} messages={selected.messages ?? []} urlFor={attachmentUrl} /><TemplatePicker slug={slug} open={templateOpen} title={t("portal.inbox.window.sendTemplate")} onClose={() => setTemplateOpen(false)} onSend={replyWithTemplate} /></>}</section></div>}</section></main>;
}
