"use client";

import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "next/navigation";
import { Download, LoaderCircle, Send, X } from "lucide-react";
import { api, apiUrl, messageFrom } from "@/lib/api";
import { AttachButton, MessageAttachments, PendingAttachment, type GalleryImage } from "@/components/attachments";
import { RichText } from "@/components/rich-text";
import { chatToText, downloadText } from "@/lib/export";
import { formatTime } from "@/lib/datetime";
import { useLanguage, useT } from "@/lib/i18n";
import type { Attachment } from "@/types";

type Config = { title: string; greeting: string; color: string; position: string; agency_name: string; logo_url: string | null };
type Msg = { role: "user" | "assistant"; content: string; created_at?: string | null; attachments?: Attachment[] };
type Reply = { mode: string; reply: string | null; reply_at?: string | null; messages: Msg[] };

// Tell the host loader (widget.js) to show a greeting teaser or an unread dot.
function notifyHost(action: string, text?: string) {
  try { window.parent?.postMessage({ type: "ol-widget", action, text }, "*"); } catch {}
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
  const openRef = useRef(false);
  const endRef = useRef<HTMLDivElement>(null);
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
      if (data.greeting) notifyHost("greeting", data.greeting);
    }).catch(() => setError("unavailable"));
  }, [publicId]);

  useEffect(() => {
    if (!session) return;
    api<Reply>(`/widget/${publicId}/history?session_id=${encodeURIComponent(session)}`).then((data) => setMessages(data.messages)).catch(() => {});
  }, [session, publicId]);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages.length, busy]);

  const attachmentUrl = (attachment: Attachment) => apiUrl(`/widget/${publicId}/attachments/${attachment.id}?session_id=${encodeURIComponent(session)}`);
  const gallery: GalleryImage[] = useMemo(
    () => messages.flatMap((message) =>
      (message.attachments ?? []).filter((a) => a.kind === "image").map((a) => ({ id: a.id, url: apiUrl(`/widget/${publicId}/attachments/${a.id}?session_id=${encodeURIComponent(session)}`), name: a.filename }))
    ),
    [messages, publicId, session],
  );

  function close() { window.parent?.postMessage({ type: "ol-widget", action: "close" }, "*"); }

  function exportChat() {
    if (!config) return;
    const transcript: typeof messages = config.greeting
      ? [{ role: "assistant", content: config.greeting }, ...messages]
      : messages;
    const text = chatToText(transcript, { title: config.title, agentLabel: config.title, visitorLabel: t("inbox.senderVisitor") });
    downloadText(text, config.title);
  }

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
    setBusy(true); setError("");
    setMessages((current) => [...current, { role: "user", content, created_at: new Date().toISOString() }]);
    try {
      const data = await api<Reply>(`/widget/${publicId}/messages`, { method: "POST", body: JSON.stringify({ session_id: session, content }) });
      if (data.reply) {
        setMessages((current) => [...current, { role: "assistant", content: data.reply as string, created_at: data.reply_at ?? new Date().toISOString() }]);
        if (!openRef.current) notifyHost("unread");
      }
    } catch (err) { setError(messageFrom(err)); } finally { setBusy(false); inputRef.current?.focus(); }
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
      if (result.messages.length) setMessages(result.messages);
    } catch (err) { setError(messageFrom(err)); } finally { setBusy(false); inputRef.current?.focus(); }
  }

  if (error === "unavailable") return <div className="widget-shell"><div className="widget-empty">Chat unavailable</div></div>;
  if (!config) return <div className="widget-shell"><div className="widget-empty"><LoaderCircle className="spin" /></div></div>;

  const color = config.color || "#635bff";
  const showGreeting = config.greeting && messages.length === 0;
  return (
    <div className="widget-shell" style={{ ["--widget-color" as string]: color }}>
      <header className="widget-head">
        <div className="widget-head-id">
          {config.logo_url ? <img src={apiUrl(config.logo_url.replace(/^\/api/, ""))} alt="" /> : <span className="widget-avatar">{config.title.slice(0, 1).toUpperCase()}</span>}
          <div><strong>{config.title}</strong><small>{config.agency_name}</small></div>
        </div>
        <div className="widget-head-actions">
          {messages.length > 0 && <button type="button" className="widget-head-btn" onClick={exportChat} title={t("chat.exportChat")} aria-label={t("chat.exportChat")}><Download size={17} /></button>}
          <button type="button" className="widget-head-btn" onClick={close} aria-label="Close"><X size={18} /></button>
        </div>
      </header>
      <div className="widget-messages">
        {showGreeting && <div className="widget-msg assistant"><div className="widget-bubble"><RichText text={config.greeting} /></div></div>}
        {messages.map((message, index) => <div key={index} className={`widget-msg ${message.role}`}><div className="widget-msg-body"><MessageAttachments attachments={message.attachments} urlFor={attachmentUrl} gallery={gallery} stamp={message.created_at ? formatTime(message.created_at, lang) : undefined} />{message.content && <div className="widget-bubble"><RichText text={message.content} />{message.created_at && <time className="msg-time">{formatTime(message.created_at, lang)}</time>}</div>}</div></div>)}
        {busy && <div className="widget-msg assistant"><div className="widget-bubble widget-typing"><i /><i /><i /></div></div>}
        <div ref={endRef} />
      </div>
      {error && error !== "unavailable" && <div className="widget-error">{error}</div>}
      {pendingFile && <PendingAttachment file={pendingFile} onCancel={() => setPendingFile(null)} />}
      <form className="widget-composer" onSubmit={send}>
        <AttachButton onFile={setPendingFile} disabled={busy || !session} title={t("chat.attachFile")} />
        <input ref={inputRef} name="message" autoComplete="off" placeholder={t("playground.composer.placeholder")} />
        <button type="submit" disabled={busy} aria-label={t("playground.composer.send")}>{busy ? <LoaderCircle className="spin" size={18} /> : <Send size={18} />}</button>
      </form>
    </div>
  );
}
