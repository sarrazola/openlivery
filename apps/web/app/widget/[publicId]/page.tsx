"use client";

import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "next/navigation";
import { LoaderCircle, Send, X } from "lucide-react";
import { api, apiUrl, messageFrom } from "@/lib/api";
import { AttachButton, MessageAttachments, PendingAttachment, type GalleryImage } from "@/components/attachments";
import { RichText } from "@/components/rich-text";
import { useT } from "@/lib/i18n";
import type { Attachment } from "@/types";

type Config = { title: string; greeting: string; color: string; position: string; agency_name: string; agency_logo_url: string | null };
type Msg = { role: "user" | "assistant"; content: string; attachments?: Attachment[] };
type Reply = { mode: string; reply: string | null; messages: Msg[] };

export default function WidgetPage() {
  const t = useT();
  const { publicId } = useParams<{ publicId: string }>();
  const [config, setConfig] = useState<Config | null>(null);
  const [messages, setMessages] = useState<Msg[]>([]);
  const [session, setSession] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const key = `ol_widget_${publicId}`;
    let value = "";
    try { value = window.localStorage.getItem(key) || ""; } catch {}
    if (!value) { value = crypto.randomUUID(); try { window.localStorage.setItem(key, value); } catch {} }
    setSession(value);
  }, [publicId]);

  useEffect(() => {
    api<Config>(`/widget/${publicId}`).then(setConfig).catch(() => setError("unavailable"));
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
    setMessages((current) => [...current, { role: "user", content }]);
    try {
      const data = await api<Reply>(`/widget/${publicId}/messages`, { method: "POST", body: JSON.stringify({ session_id: session, content }) });
      if (data.reply) setMessages((current) => [...current, { role: "assistant", content: data.reply as string }]);
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
          {config.agency_logo_url ? <img src={config.agency_logo_url} alt="" /> : <span className="widget-avatar">{config.title.slice(0, 1).toUpperCase()}</span>}
          <div><strong>{config.title}</strong><small>{config.agency_name}</small></div>
        </div>
        <button type="button" className="widget-close" onClick={close} aria-label="Close"><X size={18} /></button>
      </header>
      <div className="widget-messages">
        {showGreeting && <div className="widget-msg assistant"><div className="widget-bubble"><RichText text={config.greeting} /></div></div>}
        {messages.map((message, index) => <div key={index} className={`widget-msg ${message.role}`}><div className="widget-msg-body"><MessageAttachments attachments={message.attachments} urlFor={attachmentUrl} gallery={gallery} />{message.content && <div className="widget-bubble"><RichText text={message.content} /></div>}</div></div>)}
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
