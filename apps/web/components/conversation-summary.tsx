"use client";

import { useEffect, useRef, useState } from "react";
import { ChevronDown, FileText, LoaderCircle, RefreshCw, X } from "lucide-react";
import { api, messageFrom } from "@/lib/api";
import { formatWhen } from "@/lib/datetime";
import { useLanguage, useT } from "@/lib/i18n";

type Summary = {
  summary: string | null;
  summary_at: string | null;
  summary_by: string | null;
  message_count: number;
  current_message_count: number;
  stale: boolean;
};

/** The conversation's summary, for the team only, pinned above the thread.
 * Nothing is written until someone asks from the conversation's menu: each
 * request is a model call billed like a reply, and asking again before new
 * messages arrive returns the stored one. `requested` grows by one each time
 * the menu item is pressed; only a press made while this card is mounted
 * writes, so opening another conversation never replays an earlier one. */
export function ConversationSummary({ slug, conversationId, requested }: { slug: string; conversationId: string; requested: number }) {
  const t = useT();
  const { lang } = useLanguage();
  const [data, setData] = useState<Summary | null>(null);
  const [open, setOpen] = useState(false);
  const [hidden, setHidden] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const path = `/portal/${slug}/conversations/${conversationId}/summary`;
  // The count already seen: a remount (back to the list, then another
  // conversation) starts from the current count instead of acting on it.
  const handled = useRef(requested);

  // A stored summary shows folded when the conversation opens; reading it is free.
  useEffect(() => {
    let live = true;
    setData(null); setOpen(false); setHidden(false); setError("");
    api<Summary>(path).then((value) => { if (live) setData(value); }).catch(() => {});
    return () => { live = false; };
  }, [path]);

  async function write() {
    setBusy(true); setError(""); setHidden(false); setOpen(true);
    try { setData(await api<Summary>(path, { method: "POST", body: JSON.stringify({ language: lang === "en" ? "en" : "es" }) })); }
    catch (err) { setError(messageFrom(err)); }
    finally { setBusy(false); }
  }

  useEffect(() => {
    if (requested <= handled.current) return;
    handled.current = requested;
    write();
  }, [requested]);

  if (hidden || (!data?.summary && !busy && !error)) return null;
  const lines = (data?.summary ?? "").split("\n").map((line) => line.replace(/^\s*[-*•]\s*/, "").trim()).filter(Boolean);

  return (
    <section className={open ? "conversation-summary open" : "conversation-summary"} aria-label={t("portal.inbox.conversation.summaryTitle")}>
      <div className="conversation-summary-head">
        <button type="button" className="conversation-summary-toggle" onClick={() => setOpen((v) => !v)} aria-expanded={open}>
          <FileText size={15} />
          <strong>{t("portal.inbox.conversation.summaryTitle")}</strong>
          {busy ? <small>{t("portal.inbox.conversation.summaryWriting")}</small>
            : data?.summary_at ? <small>{data.stale ? t("portal.inbox.conversation.summaryStale") : [data.summary_by, t("portal.inbox.conversation.summaryMeta", { count: data.message_count, when: formatWhen(data.summary_at, lang) })].filter(Boolean).join(" · ")}</small> : null}
          <ChevronDown size={15} className="conversation-summary-chevron" />
        </button>
        {data?.stale && !busy && <button type="button" className="button ghost small" onClick={write}><RefreshCw size={13} /> {t("portal.inbox.conversation.summaryUpdate")}</button>}
        <button type="button" className="icon-button" onClick={() => setHidden(true)} title={t("portal.inbox.conversation.summaryClose")} aria-label={t("portal.inbox.conversation.summaryClose")}><X size={14} /></button>
      </div>
      {open && <div className="conversation-summary-body">
        {busy && <p className="muted"><LoaderCircle className="spin" size={14} /> {t("portal.inbox.conversation.summaryWriting")}</p>}
        {error && <p className="conversation-summary-error">{error}</p>}
        {!busy && lines.length > 0 && <ul>{lines.map((line, index) => <li key={index}>{line}</li>)}</ul>}
        {!busy && lines.length > 0 && <small className="muted">{t("portal.inbox.conversation.summaryPrivate")}</small>}
      </div>}
    </section>
  );
}
