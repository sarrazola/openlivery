import type { Message } from "@/types";

/** Quoted-reply snippet shown inside a bubble, mirroring WhatsApp's
 * swipe-to-reply look so operators see the same thread the customer saw. */
export function QuotedSnippet({ messages, quotedId }: { messages: Message[]; quotedId?: string | null }) {
  if (!quotedId) return null;
  const quoted = messages.find((message) => message.id === quotedId);
  if (!quoted) return null;
  const excerpt = (quoted.content || "").slice(0, 140);
  return (
    <span className="quoted-snippet">
      {quoted.sender_name && <strong>{quoted.sender_name}</strong>}
      <span>{excerpt || "…"}</span>
    </span>
  );
}

/** The business's emoji reaction to a visitor message. */
export function ReactionBadge({ emoji }: { emoji?: string | null }) {
  if (!emoji) return null;
  return <span className="reaction-badge">{emoji}</span>;
}
