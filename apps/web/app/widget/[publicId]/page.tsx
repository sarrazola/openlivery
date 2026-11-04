"use client";

import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "next/navigation";
import { ArrowLeft, Download, History, LoaderCircle, Send, X } from "lucide-react";
import { api, apiUrl, messageFrom } from "@/lib/api";
import { AttachButton, MessageAttachments, PendingAttachment, type GalleryImage } from "@/components/attachments";
import { RichText } from "@/components/rich-text";
import { chatToText, downloadText } from "@/lib/export";
import { formatTime } from "@/lib/datetime";
import { useLanguage, useT } from "@/lib/i18n";
import type { Attachment, WidgetAppearance } from "@/types";

type Config = { title: string; greeting: string; color: string; position: string; appearance: WidgetAppearance; agency_name: string; logo_url: string | null };
type Msg = { id?: string; role: "user" | "assistant"; content: string; created_at?: string | null; attachments?: Attachment[]; sender_type?: string | null; sender_name?: string | null };
type PastCase = { id: string; title: string; created_at: string; resolved_at?: string | null; message_count: number };
type Reply = { mode: string; status?: string; conversation_id?: string | null; reply: string | null; reply_at?: string | null; messages: Msg[]; previous?: PastCase[] };

// Server messages carry ids; the ones we append while sending do not. Merging
// drops the optimistic copy once its server twin arrives and never repeats
// a message the poll has already delivered.
function mergeMessages(current: Msg[], incoming: Msg[]): Msg[] {
  if (!incoming.length) return current;
  const known = new Set(current.map((m) => m.id).filter(Boolean));
  const fresh = incoming.filter((m) => !m.id || !known.has(m.id));
  if (!fresh.length) return current;
  const kept = current.filter((m) => m.id || !fresh.some((f) => f.role === m.role && f.content === m.content));
  return [...kept, ...fresh];
}

function latestStamp(messages: Msg[]): string | null {
  let last: string | null = null;
  for (const m of messages) if (m.id && m.created_at && (!last || m.created_at > last)) last = m.created_at;
  return last;
}

// A short two-note chime when a reply arrives. Browsers only allow sound after
// the visitor interacted with the page, which typing in the chat satisfies;
// when it is not allowed yet, this silently does nothing.
let audioContext: AudioContext | null = null;
function playChime() {
  try {
    audioContext = audioContext || new AudioContext();
    const ctx = audioContext;
    if (ctx.state === "suspended") { ctx.resume().catch(() => {}); return; }
    const now = ctx.currentTime;
    [[880, 0], [1174.66, 0.12]].forEach(([freq, at]) => {
      const osc = ctx.createOscillator(); const gain = ctx.createGain();
      osc.type = "sine"; osc.frequency.value = freq;
      gain.gain.setValueAtTime(0.0001, now + at);
      gain.gain.exponentialRampToValueAtTime(0.18, now + at + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.0001, now + at + 0.22);
      osc.connect(gain).connect(ctx.destination);
      osc.start(now + at); osc.stop(now + at + 0.25);
    });
  } catch {}
}

// Tell the host loader (widget.js) what it cannot see from outside the frame:
// a greeting teaser, an unread dot, the height and corners to give the frame.
function notifyHost(action: string, detail: { text?: string; height?: number; radius?: number; reveal?: boolean } = {}) {
  try { window.parent?.postMessage({ type: "ol-widget", action, ...detail }, "*"); } catch {}
}

const CORNER_RADIUS = { square: 0, soft: 8, round: 16 };

// Dark or light, for a color chosen by whoever set up the chat, so what sits
// on it stays readable. Anything but a six-digit hex reads as dark, which keeps
// the white text this chat has always had.
function isLightColor(color: string): boolean {
  const hex = /^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(color);
  if (!hex) return false;
  const [r, g, b] = hex.slice(1).map((part) => parseInt(part, 16));
  return (0.299 * r + 0.587 * g + 0.114 * b) / 255 > 0.62;
}

export default function WidgetPage() {
  const t = useT();
  const { lang } = useLanguage();
  const { publicId } = useParams<{ publicId: string }>();
  const [config, setConfig] = useState<Config | null>(null);
  const [messages, setMessages] = useState<Msg[]>([]);
  const [session, setSession] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  // The current case, its state, and the visitor's earlier cases. Cases live
  // on the server under the browser's session id; clearing site data is the
  // only way to lose them.
  const [caseId, setCaseId] = useState<string | null>(null);
  const [previous, setPrevious] = useState<PastCase[]>([]);
  const [view, setView] = useState<"chat" | "list" | "past">("chat");
  const [past, setPast] = useState<{ item: PastCase; messages: Msg[] } | null>(null);
  // Set when a case closes while the widget is open, so the fresh chat says why.
  const [justClosed, setJustClosed] = useState(false);
  // Inline, the chat sits in the page itself: nothing opens or closes it. Read
  // once: the first render shows the spinner either way, so it cannot mismatch.
  const [inline] = useState(() => typeof window !== "undefined" && new URLSearchParams(window.location.search).get("mode") === "inline");
  // Whether this visitor's chat is known yet, so a returning one does not see
  // the start card flash before their conversation.
  const [historyLoaded, setHistoryLoaded] = useState(false);
  const openRef = useRef(inline);
  const lastAtRef = useRef<string | null>(null);
  const leftStartRef = useRef(false);
  const shellRef = useRef<HTMLDivElement>(null);
  const messagesRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // The host loader toggles our visibility; track it so replies that arrive
  // while the panel is closed can raise an unread dot on the launcher.
  useEffect(() => {
    function onHostMessage(event: MessageEvent) {
      // Only the embedding page drives our open/closed state.
      if (event.source !== window.parent) return;
      const data = event.data;
      if (!data || data.type !== "ol-widget-host") return;
      if (data.action === "opened") openRef.current = true;
      if (data.action === "closed") openRef.current = false;
    }
    window.addEventListener("message", onHostMessage);
    return () => window.removeEventListener("message", onHostMessage);
  }, []);

  useEffect(() => {
    const key = `ol_widget_${publicId}`;
    let value = "";
    try { value = window.localStorage.getItem(key) || ""; } catch {}
    if (!value) { value = crypto.randomUUID(); try { window.localStorage.setItem(key, value); } catch {} }
    setSession(value);
  }, [publicId]);

  useEffect(() => {
    api<Config>(`/widget/${publicId}`).then((data) => {
      setConfig(data);
      if (data.greeting) notifyHost("greeting", { text: data.greeting });
      notifyHost("corners", { radius: CORNER_RADIUS[data.appearance.corners] });
    }).catch(() => { setError("unavailable"); notifyHost("unavailable"); });
  }, [publicId]);

  const loadHistory = useCallback(async () => {
    if (!session) return;
    const data = await api<Reply>(`/widget/${publicId}/history?session_id=${encodeURIComponent(session)}`);
    lastAtRef.current = latestStamp(data.messages);
    setMessages(data.messages);
    setCaseId(data.conversation_id ?? null);
    setPrevious(data.previous ?? []);
  }, [session, publicId]);
  // A new case opened by writing: the closed one moved to history, so the
  // notice no longer applies.
  useEffect(() => { if (caseId) setJustClosed(false); }, [caseId]);
  useEffect(() => {
    if (!session) return;
    loadHistory().catch(() => {}).finally(() => setHistoryLoaded(true));
  }, [session, loadHistory]);

  async function openPast(item: PastCase) {
    try {
      const data = await api<Reply>(`/widget/${publicId}/conversations/${item.id}?session_id=${encodeURIComponent(session)}`);
      setPast({ item, messages: data.messages });
      setView("past");
    } catch (err) { setError(messageFrom(err)); }
  }

  // Pull what arrived since the last message we know of: a person's replies
  // once they took over, or an agent's. Every few seconds while the panel is
  // open, far less often while it is closed (enough to raise the unread dot).
  const refresh = useCallback(async () => {
    if (!session) return;
    const after = lastAtRef.current ? `&after=${encodeURIComponent(lastAtRef.current)}` : "";
    const data = await api<Reply>(`/widget/${publicId}/updates?session_id=${encodeURIComponent(session)}${after}`);
    const incoming = data.messages.filter((m) => m.role !== "user");
    if (data.messages.length) {
      const newest = latestStamp(data.messages);
      if (newest && (!lastAtRef.current || newest > lastAtRef.current)) lastAtRef.current = newest;
      setMessages((current) => mergeMessages(current, data.messages));
    }
    if (incoming.length) {
      playChime();
      if (!openRef.current) notifyHost("unread");
    }
    if (data.status === "resolved" && caseId && data.conversation_id === caseId) {
      // Closed by a person or the agent: start fresh, the thread goes to history.
      setJustClosed(true);
      await loadHistory();
    }
  }, [session, publicId, caseId, loadHistory]);
  // Nothing can arrive before the visitor writes, and an inline chat loads with
  // the page for everyone who reads it, so those do not poll. The message list
  // counts too: a send that failed after the server stored it leaves no case
  // here, and a person may still answer it.
  const hasWritten = Boolean(caseId) || messages.length > 0;
  useEffect(() => {
    if (!session || !hasWritten) return;
    let tick = 0;
    const id = window.setInterval(() => {
      tick += 1;
      if (document.hidden) return;
      if (openRef.current || tick % 5 === 0) refresh().catch(() => {});
    }, 3000);
    return () => window.clearInterval(id);
  }, [session, hasWritten, refresh]);

  // Within the message list only: scrollIntoView can also move the page around
  // the frame, which is visible on load when the chat sits inline.
  useEffect(() => {
    const list = messagesRef.current;
    if (list) list.scrollTo({ top: list.scrollHeight, behavior: "smooth" });
  }, [messages.length, busy]);

  // The first screen: nothing said yet in the chat view.
  const atStart = view === "chat" && messages.length === 0 && !busy;
  // Inline, the frame is a compact card until the chat starts and a full chat
  // from then on: a case closed from the inbox must not shrink it and move the
  // page under the visitor. Set during render so the two never disagree.
  const [expanded, setExpanded] = useState(false);
  if (inline && !atStart && !expanded) setExpanded(true);
  const compact = inline && atStart && !expanded;

  useEffect(() => {
    if (!inline || !config || !historyLoaded) return;
    // Leaving the card is the visitor's doing; a chat that loads open is not.
    if (!compact) { notifyHost("chat", { reveal: leftStartRef.current }); return; }
    leftStartRef.current = true;
    const shell = shellRef.current;
    if (!shell) return;
    const report = () => notifyHost("height", { height: Math.ceil(shell.getBoundingClientRect().height) });
    report();
    const observer = new ResizeObserver(report);
    observer.observe(shell);
    return () => observer.disconnect();
  }, [inline, config, historyLoaded, compact]);

  const attachmentUrl = (attachment: Attachment) => apiUrl(`/widget/${publicId}/attachments/${attachment.id}?session_id=${encodeURIComponent(session)}`);
  const gallery: GalleryImage[] = useMemo(
    () => messages.flatMap((message) =>
      (message.attachments ?? []).filter((a) => a.kind === "image").map((a) => ({ id: a.id, url: apiUrl(`/widget/${publicId}/attachments/${a.id}?session_id=${encodeURIComponent(session)}`), name: a.filename }))
    ),
    [messages, publicId, session],
  );

  function close() { window.parent?.postMessage({ type: "ol-widget", action: "close" }, "*"); }

  // Exports the chat on screen: the live one with its greeting, or a past one.
  function exportChat(list: Msg[] = messages, withGreeting = true) {
    if (!config) return;
    const transcript: typeof messages = withGreeting && config.greeting
      ? [{ role: "assistant", content: config.greeting }, ...list]
      : list;
    const text = chatToText(transcript, { title: config.title, agentLabel: config.title, visitorLabel: t("inbox.senderVisitor") });
    downloadText(text, config.title);
  }

  // Without preventScroll the browser centers the box in the host page's window.
  function keepTyping() { inputRef.current?.focus({ preventScroll: true }); }

  async function send(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pendingFile) {
      const file = pendingFile;
      setPendingFile(null);
      await sendFile(file);
      return;
    }
    const input = inputRef.current;
    const content = input?.value.trim() || "";
    if (!content || busy || !session) return;
    if (input) input.value = "";
    await sendText(content);
  }

  async function sendText(content: string) {
    setBusy(true); setError("");
    setMessages((current) => [...current, { role: "user", content, created_at: new Date().toISOString() }]);
    try {
      const sent = await api<Reply>(`/widget/${publicId}/messages`, { method: "POST", body: JSON.stringify({ session_id: session, content }) });
      if (!caseId || (sent.conversation_id && sent.conversation_id !== caseId)) {
        // First message of a fresh chat: adopt the new case, then pull its reply.
        setCaseId(sent.conversation_id ?? null);
        await refresh();
      } else {
        // The reply, when there is one, comes back through the same channel as
        // everything else, with its id, so nothing shows twice.
        await refresh();
      }
    } catch (err) { setError(messageFrom(err)); } finally { setBusy(false); keepTyping(); }
  }

  async function sendFile(file?: File) {
    if (!file || busy || !session) return;
    setBusy(true); setError("");
    const caption = (inputRef.current?.value || "").trim();
    try {
      const data = new FormData();
      data.append("session_id", session);
      data.append("file", file);
      if (caption) data.append("caption", caption);
      const result = await api<Reply>(`/widget/${publicId}/media`, { method: "POST", body: data });
      if (inputRef.current) inputRef.current.value = "";
      if (result.conversation_id && result.conversation_id !== caseId) setCaseId(result.conversation_id);
      if (result.messages.length) { lastAtRef.current = latestStamp(result.messages); setMessages(result.messages); }
      if (result.reply) playChime();
    } catch (err) { setError(messageFrom(err)); } finally { setBusy(false); keepTyping(); }
  }

  if (error === "unavailable") return <div className="widget-shell"><div className="widget-empty">Chat unavailable</div></div>;
  if (!config || (inline && !historyLoaded)) return <div className="widget-shell"><div className="widget-empty"><LoaderCircle className="spin" /></div></div>;

  const color = config.color || "#635bff";
  const look = config.appearance;
  // Set only when chosen, so a chat with no options renders as it always has.
  const shellStyle: Record<string, string> = { "--widget-color": color, "--widget-radius": `${CORNER_RADIUS[look.corners]}px` };
  if (isLightColor(color)) shellStyle["--widget-on-color"] = "#172033";
  if (look.background) {
    shellStyle["--widget-bg"] = look.background;
    if (!isLightColor(look.background)) Object.assign(shellStyle, { "--widget-ink": "#ffffff", "--widget-muted": "rgba(255,255,255,.72)" });
  }
  const shellClass = ["widget-shell", inline && "is-inline", compact && "is-start", look.header_style === "plain" && "head-plain"].filter(Boolean).join(" ");
  const closeButton = !inline && <button type="button" className="widget-head-btn" onClick={close} aria-label="Close"><X size={18} /></button>;
  const showGreeting = config.greeting && messages.length === 0;
  const renderMessage = (message: Msg, index: number) => <div key={message.id ?? index} className={`widget-msg ${message.role}`}><div className="widget-msg-body"><MessageAttachments attachments={message.attachments} urlFor={attachmentUrl} gallery={gallery} stamp={message.created_at ? formatTime(message.created_at, lang) : undefined} />{message.sender_type === "human" && message.sender_name && <small className="widget-sender">{message.sender_name}</small>}{message.content && <div className="widget-bubble"><RichText text={message.content} />{message.created_at && <time className="msg-time">{formatTime(message.created_at, lang)}</time>}</div>}</div></div>;
  const dateOf = (iso: string) => new Date(iso).toLocaleDateString(lang === "es" ? "es" : "en", { day: "numeric", month: "short", year: "numeric" });

  if (view !== "chat") {
    return (
      <div className={shellClass} style={shellStyle}>
        <header className="widget-head">
          <div className="widget-head-id">
            <button type="button" className="widget-head-btn" onClick={() => setView(view === "past" ? "list" : "chat")} aria-label={t("chat.backToChat")}><ArrowLeft size={18} /></button>
            <div><strong>{view === "past" && past ? t("chat.chatFrom", { date: dateOf(past.item.created_at) }) : t("chat.previousChats")}</strong><small>{config.title}</small></div>
          </div>
          <div className="widget-head-actions">{view === "past" && past && past.messages.length > 0 && <button type="button" className="widget-head-btn" onClick={() => exportChat(past.messages, false)} title={t("chat.exportChat")} aria-label={t("chat.exportChat")}><Download size={17} /></button>}{closeButton}</div>
        </header>
        {view === "list"
          ? <div className="widget-case-list">
              {previous.length === 0 && <div className="widget-empty-note">{t("chat.noPreviousChats")}</div>}
              {previous.map((item) => <button type="button" key={item.id} className="widget-case-item" onClick={() => openPast(item)}><strong>{item.title}</strong><small>{dateOf(item.created_at)} · {t("chat.messagesCount", { count: item.message_count })}</small></button>)}
            </div>
          : <div className="widget-messages">{past?.messages.map(renderMessage)}</div>}
      </div>
    );
  }

  return (
    <div ref={shellRef} className={shellClass} style={shellStyle}>
      <header className="widget-head">
        <div className="widget-head-id">
          {config.logo_url ? <img src={apiUrl(config.logo_url.replace(/^\/api/, ""))} alt="" /> : <span className="widget-avatar">{config.title.slice(0, 1).toUpperCase()}</span>}
          <div><strong>{look.header_title || config.title}</strong><small>{look.header_subtitle || config.agency_name}</small></div>
        </div>
        <div className="widget-head-actions">
          {previous.length > 0 && <button type="button" className="widget-head-btn" onClick={() => setView("list")} title={t("chat.previousChats")} aria-label={t("chat.previousChats")}><History size={17} /></button>}
          {messages.length > 0 && <button type="button" className="widget-head-btn" onClick={() => exportChat()} title={t("chat.exportChat")} aria-label={t("chat.exportChat")}><Download size={17} /></button>}
          {closeButton}
        </div>
      </header>
      <div ref={messagesRef} className="widget-messages">
        {atStart && look.headline && <h1 className={`widget-headline ${look.headline_font}`}>{look.headline}</h1>}
        {showGreeting && <div className="widget-msg assistant"><div className="widget-bubble"><RichText text={config.greeting} /></div></div>}
        {justClosed && messages.length === 0 && <div className="widget-closed-note">{t("chat.closedNotice")}</div>}
        {messages.map(renderMessage)}
        {busy && <div className="widget-msg assistant"><div className="widget-bubble widget-typing"><i /><i /><i /></div></div>}
        {atStart && look.suggestions.length > 0 && <div className="widget-suggestions">{look.suggestions.map((suggestion) => <button type="button" key={suggestion} disabled={!session} onClick={() => sendText(suggestion)}>{suggestion}</button>)}</div>}
      </div>
      {error && error !== "unavailable" && <div className="widget-error">{error}</div>}
      {pendingFile && <PendingAttachment file={pendingFile} onCancel={() => setPendingFile(null)} />}
      <form className="widget-composer" onSubmit={send}>
        {!compact && <AttachButton onFile={setPendingFile} disabled={busy || !session} title={t("chat.attachFile")} />}
        <input ref={inputRef} name="message" autoComplete="off" placeholder={look.placeholder || t("playground.composer.placeholder")} />
        <button type="submit" disabled={busy} aria-label={t("playground.composer.send")}>{busy ? <LoaderCircle className="spin" size={18} /> : <Send size={18} />}</button>
      </form>
      {look.footer_note && <small className="widget-footnote">{look.footer_note}</small>}
    </div>
  );
}
