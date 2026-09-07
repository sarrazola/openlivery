/** Rules shared by inbox lists, thread actions, and native previews. */
import type { ChannelCapabilities, Conversation, ConversationFilters, ConversationStatus, Message } from "./api";

export type InboxFolder = "all" | "unread" | "mine" | "unassigned" | "ai" | "human";

export function inboxFilters(status: ConversationStatus, folder: InboxFolder, search = "", team = "", channel = ""): ConversationFilters {
  return {
    status,
    ...(status === "open" && folder === "unread" ? { unread: true } : {}),
    ...(status === "open" && folder === "mine" ? { assignee: "me" as const } : {}),
    ...(status === "open" && folder === "unassigned" ? { assignee: "none" as const } : {}),
    ...(status === "open" && (folder === "ai" || folder === "human") ? { mode: folder } : {}),
    ...(search.trim() ? { search: search.trim() } : {}),
    ...(team ? { team } : {}),
    ...(channel ? { channel } : {}),
  };
}

/** Offset pagination can overlap when inbound messages move existing rows. */
export function mergeConversationPages(previous: Conversation[], incoming: Conversation[]): Conversation[] {
  const byId = new Map(previous.map((row) => [row.id, row]));
  for (const row of incoming) byId.set(row.id, row);
  return [...byId.values()];
}

/** Closing the window on-device avoids enabling replies between polling ticks. */
type ReplyPolicy = Pick<Conversation, "channel" | "reply_window_open" | "reply_window_until" | "human_reply_window_open" | "human_reply_window_until" | "reply_block_reason" | "channel_capabilities">;

export function isSocialChannel(channel: string): boolean { return channel === "instagram" || channel === "messenger"; }

function windowIsOpen(open: boolean | undefined, until: string | null | undefined, now: number): boolean {
  return open === true && !!until && Number.isFinite(Date.parse(until)) && Date.parse(until) > now;
}

export function isReplyWindowClosed(conversation: ReplyPolicy, now = Date.now()): boolean {
  if (isSocialChannel(conversation.channel)) {
    if (conversation.reply_block_reason) return true;
    return !windowIsOpen(conversation.human_reply_window_open, conversation.human_reply_window_until, now)
      && !windowIsOpen(conversation.reply_window_open, conversation.reply_window_until, now);
  }
  if (conversation.channel !== "whatsapp_cloud") return false;
  if (conversation.reply_window_open === false) return true;
  if (!conversation.reply_window_until) return false;
  const until = Date.parse(conversation.reply_window_until);
  return Number.isFinite(until) && until <= now;
}

export function canReply(conversation: ReplyPolicy & Pick<Conversation, "mode" | "status">, now = Date.now()): boolean {
  return conversation.status !== "resolved" && conversation.mode === "human" && !isReplyWindowClosed(conversation, now);
}

export function channelCapabilities(conversation: Pick<Conversation, "channel" | "channel_capabilities">): ChannelCapabilities {
  if (isSocialChannel(conversation.channel)) return conversation.channel_capabilities || {};
  return { text: true, image: true, audio: true, video: true, file: true, ...conversation.channel_capabilities };
}

export function acceptsAttachment(channel: string, capabilities: ChannelCapabilities, mime: string): boolean {
  const kind = mime.startsWith("image/") ? "image" : mime.startsWith("audio/") ? "audio" : mime.startsWith("video/") ? "video" : "file";
  return capabilities[kind] === true && !(channel === "instagram" && kind === "file" && mime !== "application/pdf");
}

export function humanWindowOnly(conversation: ReplyPolicy, now = Date.now()): boolean {
  return isSocialChannel(conversation.channel) && !isReplyWindowClosed(conversation, now)
    && !windowIsOpen(conversation.reply_window_open, conversation.reply_window_until, now);
}

export function deliveryPresentation(status: string | null) {
  if (!status) return null;
  if (status === "read" || status === "delivered") return { label: status, icon: "checkmark-done" } as const;
  if (status === "sent") return { label: "sent", icon: "checkmark" } as const;
  if (status === "failed") return { label: "failed", icon: "alert-circle-outline" } as const;
  if (status === "pending") return { label: "pending", icon: "time-outline" } as const;
  return { label: "unknown", icon: "help-circle-outline" } as const;
}

export function canQuoteMessage(conversation: Parameters<typeof canReply>[0], message: Pick<Message, "kind" | "role">, now = Date.now()): boolean {
  return canReply(conversation, now) && conversation.channel_capabilities?.quotes !== false && (conversation.channel === "whatsapp" || conversation.channel === "whatsapp_cloud") && message.kind !== "activity" && message.role !== "system";
}

export function canReactToMessage(conversation: Parameters<typeof canReply>[0], message: Pick<Message, "kind" | "role">): boolean {
  // Reactions are separate from free-form messages and do not use the 24h window.
  return conversation.status !== "resolved" && conversation.mode === "human" && conversation.channel_capabilities?.reactions !== false && (conversation.channel === "whatsapp" || conversation.channel === "whatsapp_cloud") && message.kind !== "activity" && message.role === "user";
}

export type CannedVariables = { contact_name: string; contact_phone: string; my_name: string; business_name: string };

export function interpolateCannedReply(content: string, variables: CannedVariables): string {
  return content.replace(/\{(contact_name|contact_phone|my_name|business_name)\}/g, (match, key: keyof CannedVariables) => variables[key] || match);
}

/** A row's time follows the customer's message, never an operator action. */
export function conversationTimestamp(conversation: Pick<Conversation, "last_inbound_at" | "created_at" | "updated_at">): string {
  return conversation.last_inbound_at || conversation.created_at || conversation.updated_at;
}
