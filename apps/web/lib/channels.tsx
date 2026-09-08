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
