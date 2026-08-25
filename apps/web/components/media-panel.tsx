"use client";

import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { FileText, Link2, X } from "lucide-react";
import { AudioBubble, Lightbox, type GalleryImage } from "@/components/attachments";
import { useT } from "@/lib/i18n";
import type { Attachment, Message } from "@/types";

const URL_PATTERN = /https?:\/\/[^\s<>")\]]+/g;

/** WhatsApp-style "shared content" drawer for a conversation: everything sent
 * in the chat grouped into Media (images/videos), Links, and Docs tabs. */
export function MediaPanel({ open, onClose, messages, urlFor }: {
  open: boolean;
  onClose: () => void;
  messages: Message[];
  urlFor: (attachment: Attachment) => string;
}) {
  const t = useT();
  const [tab, setTab] = useState<"media" | "links" | "docs">("media");
  const [previewIndex, setPreviewIndex] = useState<number | null>(null);

  // Newest first, like WhatsApp's shared-content view.
  const media = useMemo(
    () => messages.flatMap((message) => (message.attachments ?? []).filter((a) => a.kind === "image" || a.kind === "video" || a.kind === "audio")).reverse(),
    [messages],
  );
  // Docs = plain files (pdf/txt/…) — anything that is not media or a link.
  const docs = useMemo(
    () => messages.flatMap((message) => (message.attachments ?? []).filter((a) => a.kind === "file")).reverse(),
    [messages],
  );
  const links = useMemo(() => {
    const seen = new Set<string>();
    const found: string[] = [];
    for (const message of messages) {
      for (const url of message.content?.match(URL_PATTERN) ?? []) {
        if (!seen.has(url)) { seen.add(url); found.push(url); }
      }
    }
    return found.reverse();
  }, [messages]);
  const gallery: GalleryImage[] = useMemo(
    () => media.filter((a) => a.kind === "image").map((a) => ({ id: a.id, url: urlFor(a), name: a.filename })),
    [media, urlFor],
  );

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => { if (event.key === "Escape" && previewIndex === null) onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose, previewIndex]);

  if (!open) return null;
  return createPortal(
    <div className="media-panel-backdrop" onClick={onClose}>
      <aside className="media-panel" onClick={(event) => event.stopPropagation()}>
        <header>
          <strong>{t("chat.sharedContent")}</strong>
          <button type="button" onClick={onClose} aria-label={t("chat.closePreview")}><X size={18} /></button>
        </header>
        <div className="inbox-tabs">
          <button className={tab === "media" ? "active" : ""} onClick={() => setTab("media")}>{t("chat.tabMedia")}</button>
          <button className={tab === "links" ? "active" : ""} onClick={() => setTab("links")}>{t("chat.tabLinks")}</button>
          <button className={tab === "docs" ? "active" : ""} onClick={() => setTab("docs")}>{t("chat.tabDocs")}</button>
        </div>
        <div className="media-panel-body">
          {tab === "media" && (media.length ? (
            <div className="media-panel-grid">
              {media.map((attachment) => attachment.kind === "image" ? (
                <button
                  key={attachment.id}
                  type="button"
                  onClick={() => setPreviewIndex(Math.max(0, gallery.findIndex((item) => item.id === attachment.id)))}
                >
                  <img src={urlFor(attachment)} alt={attachment.filename || "attachment"} loading="lazy" />
                </button>
              ) : attachment.kind === "audio" ? (
                <div key={attachment.id} className="media-panel-audio"><AudioBubble src={urlFor(attachment)} /></div>
              ) : (
                <video key={attachment.id} src={urlFor(attachment)} controls preload="metadata" />
              ))}
            </div>
          ) : <p className="media-panel-empty">{t("chat.emptyShared")}</p>)}
          {tab === "links" && (links.length ? (
            <ul className="media-panel-links">
              {links.map((url) => (
                <li key={url}>
                  <a href={url} target="_blank" rel="noreferrer">
                    <span className="media-panel-link-icon"><Link2 size={15} /></span>
                    <span><strong>{new URL(url).hostname.replace(/^www\./, "")}</strong><small>{url}</small></span>
                  </a>
                </li>
              ))}
            </ul>
          ) : <p className="media-panel-empty">{t("chat.emptyShared")}</p>)}
          {tab === "docs" && (docs.length ? (
            <ul className="media-panel-links">
              {docs.map((attachment) => (
                <li key={attachment.id}>
                  <a href={urlFor(attachment)} target="_blank" rel="noreferrer">
                    <span className="media-panel-link-icon"><FileText size={15} /></span>
                    <span><strong>{attachment.filename || "file"}</strong><small>{attachment.mime}</small></span>
                  </a>
                </li>
              ))}
            </ul>
          ) : <p className="media-panel-empty">{t("chat.emptyShared")}</p>)}
        </div>
      </aside>
      {previewIndex !== null && (
        <Lightbox items={gallery} index={previewIndex} onIndex={setPreviewIndex} onClose={() => setPreviewIndex(null)} />
      )}
    </div>,
    document.body,
  );
}
