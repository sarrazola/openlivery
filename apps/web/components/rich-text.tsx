"use client";

import { Fragment, ReactNode } from "react";

// Lightweight markdown for chat bubbles: bold, italics, inline code, links and
// bullet/numbered lists — the subset LLM replies actually use. Everything is
// rendered with inline elements (block-styled via CSS) so it stays valid inside
// any bubble wrapper, including <p>.
const INLINE = /(\*\*[^*\n]+\*\*|\*[^*\n]+\*|`[^`\n]+`|\[[^\]\n]+\]\(https?:\/\/[^)\s]+\)|https?:\/\/[^\s<>")\]]+)/g;

function renderInline(text: string, keyPrefix: string): ReactNode[] {
  return text.split(INLINE).filter(Boolean).map((part, index) => {
    const key = `${keyPrefix}-${index}`;
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4) {
      return <strong key={key}>{part.slice(2, -2)}</strong>;
    }
    if (part.startsWith("`") && part.endsWith("`") && part.length > 2) {
      return <code key={key}>{part.slice(1, -1)}</code>;
    }
    if (part.startsWith("*") && part.endsWith("*") && part.length > 2) {
      return <em key={key}>{part.slice(1, -1)}</em>;
    }
    const link = part.match(/^\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)$/);
    if (link) {
      return <a key={key} href={link[2]} target="_blank" rel="noreferrer">{link[1]}</a>;
    }
    // Bare URLs (what customers actually paste) become clickable links.
    if (/^https?:\/\//.test(part)) {
      return <a key={key} href={part} target="_blank" rel="noreferrer">{part}</a>;
    }
    return <Fragment key={key}>{part}</Fragment>;
  });
}

export function RichText({ text }: { text: string }) {
  const lines = text.split("\n");
  return (
    <span className="rich-text">
      {lines.map((line, index) => {
        const key = `line-${index}`;
        if (!line.trim()) return <span key={key} className="rt-gap" />;
        const bullet = line.match(/^\s*[-*•]\s+(.*)$/);
        if (bullet) {
          return <span key={key} className="rt-li" data-marker="•">{renderInline(bullet[1], key)}</span>;
        }
        const numbered = line.match(/^\s*(\d+)[.)]\s+(.*)$/);
        if (numbered) {
          return <span key={key} className="rt-li" data-marker={`${numbered[1]}.`}>{renderInline(numbered[2], key)}</span>;
        }
        return <span key={key} className="rt-line">{renderInline(line, key)}</span>;
      })}
    </span>
  );
}
