"use client";

import { useEffect, useState } from "react";
import { Clock } from "lucide-react";
import { isSocialChannel } from "@/lib/channels";
import { useT } from "@/lib/i18n";
import type { Conversation } from "@/types";

/** Apply server decisions and expire cached windows while a thread stays open. */
export function useReplyPolicy(conversation: Conversation | null) {
  const [now, setNow] = useState(Date.now);
  const social = isSocialChannel(conversation?.channel);
  useEffect(() => {
    if (!social && conversation?.channel !== "whatsapp_cloud") return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [social, conversation?.channel]);
  const alive = (until?: string | null) => !until || Date.parse(until) > now;
  const standardOpen = conversation?.reply_window_open === true && alive(conversation.reply_window_until);
  const humanOpen = conversation?.human_reply_window_open === true && alive(conversation.human_reply_window_until);
  const blocked = social
    ? (!standardOpen && !humanOpen) || Boolean(conversation?.reply_block_reason && conversation.reply_block_reason !== "reply_window_closed")
    : conversation?.channel === "whatsapp_cloud" && (conversation.reply_window_open === false || !alive(conversation.reply_window_until));
  const canReply = Boolean(conversation) && conversation?.mode === "human" && conversation.status !== "resolved" && !blocked;
  const capabilities = conversation?.channel_capabilities;
  const canAttach = canReply && (!social || Boolean(capabilities?.image || capabilities?.video || capabilities?.file || capabilities?.audio));
  const canRecord = canReply && (!social || capabilities?.audio === true);
  return { social, blocked, humanOnly: social && !standardOpen && humanOpen && !blocked, canReply, canAttach, canRecord };
}

export function SocialReplyNotice({ conversation, blocked, humanOnly }: { conversation: Conversation; blocked: boolean; humanOnly: boolean }) {
  const t = useT();
  if (!isSocialChannel(conversation.channel) || (!blocked && !humanOnly)) return null;
  const reason = conversation.reply_block_reason;
  const hint = reason === "channel_disconnected" || reason === "authorization_expired"
    ? "social.reconnectHint" : reason === "another_app_controls_conversation"
      ? "social.controlHint" : blocked && conversation.reply_window_open === undefined
        ? "social.policyUnavailable" : blocked ? "social.windowClosedHint" : "social.humanWindowHint";
  return <div className={`reply-policy-notice ${blocked ? "closed" : "human"}`} role="status"><Clock size={16} /><div><strong>{t(blocked ? "social.windowClosed" : "social.humanWindow")}</strong><small>{t(hint)}</small></div></div>;
}
