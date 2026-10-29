"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { ChevronDown, MessageCircle, Phone, Plus } from "lucide-react";
import { useT } from "@/lib/i18n";

/** "New agent" with the kind picked before the wizard opens: a chat agent
 * answers messages, a voice agent answers phone calls and has its own path. */
export function NewAgentMenu({ clientId, label }: { clientId?: string; label: string }) {
  const t = useT();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const go = (kind: "chat" | "voice") => {
    setOpen(false);
    const params = new URLSearchParams();
    if (clientId) params.set("client", clientId);
    if (kind === "voice") params.set("kind", "voice");
    const query = params.toString();
    router.push(`/agents/new${query ? `?${query}` : ""}`);
  };
  return <div className="start-line-wrap">
    <button type="button" className="button primary" aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen((v) => !v)}><Plus size={17} /> {label} <ChevronDown size={15} /></button>
    {open && <>
      <div className="menu-backdrop" onClick={() => setOpen(false)} />
      <div className="start-line-menu new-agent-menu" role="menu">
        <button type="button" role="menuitem" onClick={() => go("chat")}><span className="channel-dot chat"><MessageCircle size={14} /></span><span><strong>{t("phone.agent.menuChat")}</strong><small>{t("phone.agent.kindChatCopy")}</small></span></button>
        <button type="button" role="menuitem" onClick={() => go("voice")}><span className="channel-dot voice"><Phone size={14} /></span><span><strong>{t("phone.agent.menuVoice")}</strong><small>{t("phone.agent.kindVoiceCopy")}</small></span></button>
      </div>
    </>}
  </div>;
}
