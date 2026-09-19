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

/** The number or handle an account is known by, with the operator's label
 * beside it when there is one: "+57 321 788 7609 · COL". Before the account
 * is linked there is no number, so the name alone. */
export function accountTitle(channel: NamedAccount, fallback: string): string {
  const label = (channel.label || "").trim();
  const phone = (channel.phone_number || "").trim();
  const primary = phone ? (phone.startsWith("+") ? phone : `+${phone}`)
    : channel.username ? `@${channel.username.replace(/^@/, "")}` : (channel.display_name || "").trim();
  if (!primary) return label || fallback;
  return label && label !== primary ? `${primary} · ${label}` : primary;
}

/** Which of a client's accounts a channel page opens on. `?line=<id>` names
 * one and `?new` starts another; with neither, the first account. */
export function requestedLine(): { line: string | null; adding: boolean } {
  if (typeof window === "undefined") return { line: null, adding: false };
  const params = new URLSearchParams(window.location.search);
  return { line: params.get("line"), adding: params.has("new") };
}

type Translate = (key: I18nKey, vars?: Record<string, string | number>) => string;

/** The state dot tone for Meta's quality rating of a WhatsApp number. */
export function qualityTone(rating?: string | null): "connected" | "pending" | "disconnected" | "off" {
  const value = (rating || "").toUpperCase();
  return value === "GREEN" ? "connected" : value === "YELLOW" ? "pending" : value === "RED" ? "disconnected" : "off";
}

export function qualityLabel(rating: string | null | undefined, t: Translate): string {
  const value = (rating || "").toUpperCase();
  return value === "GREEN" ? t("clients.whatsappCloud.qualityGreen")
    : value === "YELLOW" ? t("clients.whatsappCloud.qualityYellow")
    : value === "RED" ? t("clients.whatsappCloud.qualityRed") : t("clients.whatsappCloud.qualityUnknown");
}

/** Meta's messaging limit tier as a sentence: business-initiated
 * conversations the number may open in 24 hours. */
export function messagingLimitLabel(tier: string | null | undefined, t: Translate): string | null {
  const counts: Record<string, number> = { TIER_50: 50, TIER_250: 250, TIER_1K: 1000, TIER_10K: 10000, TIER_100K: 100000 };
  const value = (tier || "").toUpperCase();
  if (!value) return null;
  if (value === "TIER_UNLIMITED") return t("clients.whatsappCloud.limitUnlimited");
  const count = counts[value];
  return count ? t("clients.whatsappCloud.limitLabel", { n: count.toLocaleString() }) : null;
}

/** Keep the open account in the address, so a reload or a return from a
 * provider's authorization lands on it; `null` while a new one is set up. */
export function rememberLine(id: string | null) {
  if (typeof window === "undefined") return;
  const url = new URL(window.location.href);
  url.searchParams.delete("new");
  if (id) url.searchParams.set("line", id); else url.searchParams.delete("line");
  window.history.replaceState(window.history.state, "", url.pathname + url.search + url.hash);
}
