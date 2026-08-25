import type { Conversation } from "@/types";

/** Relative-ish timestamps for inbox rows and bubbles. */
export function formatWhen(iso: string, locale: string = "en"): string {
  const date = new Date(iso);
  const time = date.toLocaleTimeString(locale, { hour: "2-digit", minute: "2-digit" });
  const sameDay = date.toDateString() === new Date().toDateString();
  if (sameDay) return time;
  const day = date.toLocaleDateString(locale, { day: "numeric", month: "short" });
  return `${day} · ${time}`;
}

/** Clock time only (e.g. "4:16 PM"), for the WhatsApp-style stamp inside bubbles. */
export function formatTime(iso: string, locale: string = "en"): string {
  return new Date(iso).toLocaleTimeString(locale, { hour: "numeric", minute: "2-digit" });
}

/** True when a poll result should not replace the open thread (avoids scroll jumps). */
export function isSameOpenThread(prev: Conversation | null, next: Conversation): boolean {
  if (!prev || prev.id !== next.id || prev.mode !== next.mode) return false;
  const prevMessages = prev.messages ?? [];
  const nextMessages = next.messages ?? [];
  if (prevMessages.length !== nextMessages.length) return false;
  return prevMessages.at(-1)?.id === nextMessages.at(-1)?.id;
}

/** True when the scroll container is near the bottom (within a threshold). */
export function isNearBottom(el: HTMLElement, threshold: number = 150): boolean {
  return el.scrollHeight - el.scrollTop - el.clientHeight < threshold;
}
