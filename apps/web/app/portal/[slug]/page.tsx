"use client";

import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "next/navigation";
import { BadgeCheck, Bot, Building2, FlaskConical, Globe, Images, Inbox, LoaderCircle, LogOut, MessageCircle, MessageSquareText, Search, Send, ShieldCheck, UserRound } from "lucide-react";
import { AttachButton, MessageAttachments, PendingAttachment, RecordButton, useFileDrop, type GalleryImage } from "@/components/attachments";
import { LanguageSwitcher } from "@/components/language-switcher";
import { MediaPanel } from "@/components/media-panel";
import { RichText } from "@/components/rich-text";
import { Alert, EmptyState } from "@/components/ui";
import { api, ApiError, apiUrl, messageFrom } from "@/lib/api";
import { formatTime, formatWhen, isNearBottom, isSameOpenThread } from "@/lib/datetime";
import { useLanguage, useT } from "@/lib/i18n";
import type { Attachment, Conversation, PortalPublic } from "@/types";

const POLL_MS = 8000;

type Session = { client_id: string; client_name: string; portal_slug: string; agency_name: string };

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
  return <PortalInbox slug={slug} portal={portal} logout={logout} />;
}

function PortalInbox({ slug, portal, logout }: { slug: string; portal: PortalPublic; logout: () => void }) {
  const t = useT();
  const { lang } = useLanguage();
  const [items, setItems] = useState<Conversation[]>([]);
  const [selected, setSelected] = useState<Conversation | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const [tab, setTab] = useState<"all" | "human" | "ai">("all");
  const [search, setSearch] = useState("");
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
  const visible = items.filter((item) =>
    (tab === "all" || item.mode === tab)
    && (!search.trim() || `${item.title} ${item.preview || ""}`.toLowerCase().includes(search.trim().toLowerCase()))
  );
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

  const refresh = useCallback(async () => {
    const rows = await api<Conversation[]>(`/portal/${slug}/conversations`);
    setItems(rows);
    const openId = selectedIdRef.current ?? rows[0]?.id;
    if (!openId) return;
    const conv = await api<Conversation>(`/portal/${slug}/conversations/${openId}`);
    if (selectedIdRef.current && selectedIdRef.current !== openId) return;
    setSelected((prev) => (isSameOpenThread(prev, conv) ? prev : conv));
  }, [slug]);

  useEffect(() => { refresh().catch((err) => setError(messageFrom(err))); }, [refresh]);
  useEffect(() => {
    const id = setInterval(() => { refresh().catch(() => {}); }, POLL_MS);
    return () => clearInterval(id);
  }, [refresh]);

  async function choose(item: Conversation) {
    selectedIdRef.current = item.id;
    setSelected(await api<Conversation>(`/portal/${slug}/conversations/${item.id}`));
  }
  async function setMode(mode: "ai" | "human") { if (!selected) return; setSelected(await api<Conversation>(`/portal/${slug}/conversations/${selected.id}/mode`, { method: "PATCH", body: JSON.stringify({ mode }) })); await refresh(); }
  async function reply(event: FormEvent<HTMLFormElement>) { event.preventDefault(); if (!selected) return; if (pendingFile) { const file = pendingFile; setPendingFile(null); await sendAttachment(file); return; } const form = event.currentTarget; const data = new FormData(form); setBusy(true); setError(""); try { setSelected(await api<Conversation>(`/portal/${slug}/conversations/${selected.id}/reply`, { method: "POST", body: JSON.stringify({ content: data.get("content") }) })); form.reset(); await refresh(); } catch (err) { setError(messageFrom(err)); } finally { setBusy(false); } }
  const replyInputRef = useRef<HTMLInputElement>(null);
  async function sendAttachment(file?: File) {
    if (!file || !selected || selected.mode !== "human" || busy) return;
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
  const { dropProps, overlay } = useFileDrop(setPendingFile, { enabled: Boolean(selected) && selected?.mode === "human" && !busy, label: t("chat.dropToSend") });

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
  return <main className="portal-app" style={{ "--portal-color": portal.agency_brand_color } as React.CSSProperties}><aside className="portal-nav"><div className="portal-brand">{portal.client_logo_url || portal.agency_logo_url ? <img src={`${portal.client_logo_url || portal.agency_logo_url}`} alt="Logo" /> : <span>{portal.client_name.slice(0, 1)}</span>}<strong>{portal.client_name}</strong></div><nav><a className="active"><Inbox size={18} /> {t("portal.inbox.nav.inbox")}</a><a className="disabled"><Bot size={18} /> {t("portal.inbox.nav.agents")}</a></nav><LanguageSwitcher /><button onClick={logout}><LogOut size={17} /> {t("portal.inbox.nav.logout")}</button></aside><section className="portal-main"><header><div><small>{t("portal.inbox.header.eyebrow")}</small><h1>{portal.portal_title}</h1></div><span>{t("portal.inbox.header.conversationsCount", { count: items.length })}</span></header>{items.length ? <div className="portal-inbox"><aside>
      <div className="inbox-search"><Search size={16} /><input value={search} onChange={(e) => setSearch(e.target.value)} placeholder={t("inbox.searchPlaceholder")} /></div>
      <div className="inbox-tabs">
        <button className={tab === "all" ? "active" : ""} onClick={() => setTab("all")}>{t("inbox.tabAll")}</button>
        <button className={tab === "human" ? "active" : ""} onClick={() => setTab("human")}>{t("inbox.statusHuman")}</button>
        <button className={tab === "ai" ? "active" : ""} onClick={() => setTab("ai")}>{t("inbox.statusAi")}</button>
      </div>
      {visible.map((item) => <button key={item.id} onClick={() => choose(item)} className={selected?.id === item.id ? "active" : ""}><span className="entity-avatar tiny"><UserRound size={15} /></span><span><span className="portal-inbox-row-top"><strong>{item.title}</strong><time>{formatWhen(item.updated_at, lang)}</time></span><small className="portal-inbox-preview">{item.preview || t("portal.inbox.list.noMessages")}</small><small className="inbox-row-meta"><span className={`channel-dot ${item.channel}`}>{channelIcon(item.channel)}</span> {channelLabel(item.channel)} <span className={`mini-badge ${item.mode}`}>{item.mode === "human" ? t("portal.inbox.list.humanSupport") : t("portal.inbox.list.aiAgent")}</span></small></span></button>)}
      {!visible.length && <div className="no-conversations">{t("inbox.empty")}</div>}
    </aside><section className="drop-target" {...dropProps}>{overlay}{selected && <><header><div><strong>{selected.title}</strong><small className="portal-channel-line">{channelIcon(selected.channel)} {channelLabel(selected.channel)} <span className={`mini-badge ${selected.mode}`}>{selected.mode === "human" ? t("portal.inbox.list.humanSupport") : t("portal.inbox.list.aiAgent")}</span></small></div><div className="thread-actions"><button className="icon-button" onClick={() => setMediaOpen(true)} title={t("chat.sharedContent")} aria-label={t("chat.sharedContent")}><Images size={16} /></button><button className={`mode-toggle ${selected.mode}`} onClick={() => setMode(selected.mode === "ai" ? "human" : "ai")}>{selected.mode === "ai" ? t("portal.inbox.conversation.takeControl") : t("portal.inbox.conversation.returnToAi")}</button></div></header><div className="portal-messages" ref={messagesRef}>{selected.messages?.map((message, index) => {
              const prev = index > 0 ? selected.messages![index - 1] : null;
              const grouped = Boolean(prev && prev.role === message.role && prev.sender_name === message.sender_name);
              const stamp = formatTime(message.created_at, lang);
              const hasAudio = message.attachments?.some((a) => a.kind === "audio");
              return <article key={message.id} className={`${message.role}${grouped ? " grouped" : ""}`}>
                {!grouped && <small>{message.sender_name || (message.role === "assistant" ? t("portal.inbox.conversation.agent") : t("portal.inbox.conversation.visitor"))}</small>}
                <MessageAttachments attachments={message.attachments} urlFor={attachmentUrl} gallery={gallery} stamp={stamp} />
                {message.content ? <p><RichText text={message.content} /><time className="msg-time">{stamp}</time></p>
                  : !hasAudio && message.attachments?.length ? <time className="msg-time bare">{stamp}</time> : null}
              </article>;
            })}</div>{error && <Alert>{error}</Alert>}{pendingFile && <PendingAttachment file={pendingFile} onCancel={() => setPendingFile(null)} />}<form onSubmit={reply} className="portal-composer"><AttachButton onFile={setPendingFile} disabled={selected.mode !== "human" || busy} title={t("chat.attachFile")} /><RecordButton onRecorded={sendAttachment} onError={() => setError(t("chat.micDenied"))} disabled={selected.mode !== "human" || busy} title={t("chat.recordAudio")} titleStop={t("chat.stopRecording")} /><input ref={replyInputRef} name="content" required={!pendingFile} disabled={selected.mode !== "human" || busy} placeholder={selected.mode === "human" ? t("portal.inbox.conversation.replyPlaceholder") : t("portal.inbox.conversation.takeControlToReply")} /><button disabled={selected.mode !== "human" || busy}>{busy ? <LoaderCircle className="spin" size={18} /> : <Send size={18} />}</button></form><MediaPanel open={mediaOpen} onClose={() => setMediaOpen(false)} messages={selected.messages ?? []} urlFor={attachmentUrl} /></>}</section></div> : <EmptyState icon={<Inbox />} title={t("portal.inbox.empty.title")} description={t("portal.inbox.empty.description")} />}</section></main>;
}
