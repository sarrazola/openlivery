import { BadgeCheck, Facebook, FlaskConical, Globe, Instagram, MessageCircle } from "lucide-react";
import type { I18nKey } from "@/lib/i18n";

export const INBOX_CHANNELS = ["whatsapp", "whatsapp_cloud", "instagram", "messenger", "widget", "playground"] as const;
const labels: Record<string, I18nKey> = {
  whatsapp: "inbox.channelWhatsapp",
  whatsapp_cloud: "inbox.channelWhatsappCloud",
  instagram: "social.instagram.title",
  messenger: "social.messenger.title",
  widget: "inbox.channelWidget",
  playground: "inbox.channelPlayground",
};

export function channelLabel(value: string, t: (key: I18nKey) => string): string {
  return labels[value] ? t(labels[value]) : value;
}

export function ChannelIcon({ channel, size = 10 }: { channel: string; size?: number }) {
  const Icon = channel === "instagram" ? Instagram : channel === "messenger" ? Facebook
    : channel === "whatsapp_cloud" ? BadgeCheck : channel === "widget" ? Globe
    : channel === "playground" ? FlaskConical : MessageCircle;
  return <Icon size={size} />;
}

export function isSocialChannel(channel?: string): boolean {
  return channel === "instagram" || channel === "messenger";
}

/** The last digits of a number, however the provider formatted it. */
export function phoneSuffix(phone?: string | null, digits = 4): string | null {
  const only = (phone || "").replace(/\D/g, "");
  return only.length >= digits ? only.slice(-digits) : null;
}

type NamedAccount = { label?: string | null; phone_number?: string | null; display_name?: string | null; username?: string | null };

/** What to call one of a client's accounts: the operator's label, else the
 * number's last digits or the handle, else ``fallback`` (e.g. "Line 2"). */
export function accountName(channel: NamedAccount, fallback: string): string {
  const label = (channel.label || "").trim();
  if (label) return label;
  const suffix = phoneSuffix(channel.phone_number);
  if (suffix) return `\u00b7\u00b7\u00b7${suffix}`;
  if (channel.username) return `@${channel.username.replace(/^@/, "")}`;
  return channel.display_name || fallback;
}
