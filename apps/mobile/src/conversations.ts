/**
 * What to call a conversation.
 *
 * The title the server stores is the first thing the customer typed, which is
 * fine as a database label and wrong as a name: a chat headed "hola prueba"
 * tells you nothing about who is writing, and the last message is already on
 * the row underneath. So the name is the person, the way it is in any
 * messaging app - and when nobody gave a name, the next most identifying thing
 * the channel knows.
 */

import type { Conversation } from "./api";
import type { Strings as Dictionary } from "./i18n";

/** `573001234567@s.whatsapp.net` -> `+573001234567`. */
export function phoneFrom(externalChatId: string | null | undefined): string | null {
  const digits = (externalChatId || "").split("@")[0].replace(/\D/g, "");
  // Short enough to be a group id or a placeholder rather than a number.
  return digits.length >= 7 ? `+${digits}` : null;
}

export function isWhatsApp(channel: string): boolean {
  return channel === "whatsapp" || channel === "whatsapp_cloud";
}

export function channelLabel(channel: string, s: Dictionary): string {
  if (isWhatsApp(channel)) return s.channels.whatsapp;
  if (channel === "widget") return s.channels.widget;
  if (channel === "playground") return s.channels.playground;
  return channel;
}

/** Who this conversation is with. */
export function conversationName(
  conversation: Pick<Conversation, "contact_name" | "channel" | "external_chat_id" | "title">,
  s: Dictionary,
): string {
  const named = (conversation.contact_name || "").trim();
  if (named) return named;
  if (isWhatsApp(conversation.channel)) {
    const phone = phoneFrom(conversation.external_chat_id);
    if (phone) return phone;
  }
  if (conversation.channel === "widget") return s.list.webVisitor;
  return (conversation.title || "").trim() || s.list.untitled;
}

/** The letter shown in the avatar when there is no picture. */
export function initialFor(name: string): string {
  const letter = name.replace(/^\+/, "").trim().slice(0, 1).toUpperCase();
  return letter || "?";
}
