"use client";

import { CircleHelp } from "lucide-react";

// A small "?" next to a label or section title: hover or focus it to read, in
// one line, what the AI receives from that field. Used wherever a value ends
// up in the agent's prompt, so the agency never has to guess.
export function AiHint({ text }: { text: string }) {
  return (
    <span className="ai-hint" tabIndex={0} role="note" aria-label={text}>
      <CircleHelp size={14} />
      <span className="ai-hint-tip">{text}</span>
    </span>
  );
}
