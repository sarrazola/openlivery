/** Rules shared by inbox lists, thread actions, and native previews. */
import type { Conversation, ConversationFilters, ConversationStatus, Message } from "./api";

export type InboxFolder = "all" | "unread" | "mine" | "unassigned" | "ai" | "human";

export function inboxFilters(status: ConversationStatus, folder: InboxFolder, search = "", team = ""): ConversationFilters {
  return {
    status,
    ...(status === "open" && folder === "unread" ? { unread: true } : {}),
    ...(status === "open" && folder === "mine" ? { assignee: "me" as const } : {}),
    ...(status === "open" && folder === "unassigned" ? { assignee: "none" as const } : {}),
    ...(status === "open" && (folder === "ai" || folder === "human") ? { mode: folder } : {}),
    ...(search.trim() ? { search: search.trim() } : {}),
    ...(team ? { team } : {}),
  };
}

/** Offset pagination can overlap when inbound messages move existing rows. */
export function mergeConversationPages(previous: Conversation[], incoming: Conversation[]): Conversation[] {
  const byId = new Map(previous.map((row) => [row.id, row]));
  for (const row of incoming) byId.set(row.id, row);
  return [...byId.values()];
}

/** Closing the window on-device avoids enabling replies between polling ticks. */
export function isReplyWindowClosed(conversation: Pick<Conversation, "channel" | "reply_window_open" | "reply_window_until">, now = Date.now()): boolean {
  if (conversation.channel !== "whatsapp_cloud") return false;
  if (conversation.reply_window_open === false) return true;
  if (!conversation.reply_window_until) return false;
  const until = Date.parse(conversation.reply_window_until);
  return Number.isFinite(until) && until <= now;
}

export function canReply(conversation: Pick<Conversation, "mode" | "status" | "channel" | "reply_window_open" | "reply_window_until">, now = Date.now()): boolean {
  return conversation.status !== "resolved" && conversation.mode === "human" && !isReplyWindowClosed(conversation, now);
}

export function canQuoteMessage(conversation: Parameters<typeof canReply>[0], message: Pick<Message, "kind" | "role">, now = Date.now()): boolean {
  return canReply(conversation, now) && (conversation.channel === "whatsapp" || conversation.channel === "whatsapp_cloud") && message.kind !== "activity" && message.role !== "system";
}

export function canReactToMessage(conversation: Parameters<typeof canReply>[0], message: Pick<Message, "kind" | "role">): boolean {
  // Reactions are separate from free-form messages and do not use the 24h window.
  return conversation.status !== "resolved" && conversation.mode === "human" && (conversation.channel === "whatsapp" || conversation.channel === "whatsapp_cloud") && message.kind !== "activity" && message.role === "user";
}

export type CannedVariables = { contact_name: string; contact_phone: string; my_name: string; business_name: string };

export function interpolateCannedReply(content: string, variables: CannedVariables): string {
  return content.replace(/\{(contact_name|contact_phone|my_name|business_name)\}/g, (match, key: keyof CannedVariables) => variables[key] || match);
}

/** A row's time follows the customer's message, never an operator action. */
export function conversationTimestamp(conversation: Pick<Conversation, "last_inbound_at" | "created_at" | "updated_at">): string {
  return conversation.last_inbound_at || conversation.created_at || conversation.updated_at;
}
