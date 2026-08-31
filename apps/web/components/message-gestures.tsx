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

/** An emoji reaction under a bubble: the business's on a visitor message, or
 * the customer's (`incoming`) on the business's own message. */
export function ReactionBadge({ emoji, incoming }: { emoji?: string | null; incoming?: boolean }) {
  if (!emoji) return null;
  return <span className={`reaction-badge${incoming ? " incoming" : ""}`}>{emoji}</span>;
}

const REACTION_CHOICES = ["👍", "❤️", "😂", "🙌", "🎉", "🙏"];

/** Small emoji palette shown next to a visitor message; picking the current
 * emoji again (or the remove option) clears the reaction. */
export function ReactionPicker({
  current,
  onPick,
  removeLabel,
}: {
  current?: string | null;
  onPick: (emoji: string) => void;
  removeLabel: string;
}) {
  return (
    <span className="reaction-picker" role="menu">
      {REACTION_CHOICES.map((emoji) => (
        <button
          key={emoji}
          type="button"
          className={current === emoji ? "active" : ""}
          onClick={() => onPick(current === emoji ? "" : emoji)}
        >
          {emoji}
        </button>
      ))}
      {current && (
        <button type="button" className="remove" onClick={() => onPick("")}>
          {removeLabel}
        </button>
      )}
    </span>
  );
}
