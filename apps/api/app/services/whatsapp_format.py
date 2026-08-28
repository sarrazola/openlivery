"""Outbound WhatsApp text shaping.

LLMs write Markdown, but WhatsApp has its own inline syntax (*bold*, _italic_,
~strikethrough~, ```monospace```) and renders everything else literally — a
customer would see the raw asterisks of ``**bold**``. Stored messages keep
their Markdown (the portal renders it); only the copy sent through a WhatsApp
channel is converted here.

This module also parses the optional "gesture" directives the agent may prefix
its reply with ([react: 👍] / [quote: N]); the pipeline turns them into a Meta
reaction or a quoted reply and strips them from the delivered text.
"""

import re

_BOLD = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)
_BOLD_ALT = re.compile(r"__(.+?)__", re.DOTALL)
_STRIKE = re.compile(r"~~(.+?)~~", re.DOTALL)
_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.*)$")
_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^\s)]+)\)")
_BULLET = re.compile(r"^(\s*)\*\s+")
_TABLE_SEPARATOR = re.compile(r"^\s*\|?[\s:|-]+\|[\s:|-]*$")


def markdown_to_whatsapp(text: str) -> str:
    """Best-effort Markdown → WhatsApp formatting. Unknown constructs are left
    as-is; the goal is that nothing renders as raw markup on a phone."""
    if not text:
        return text
    lines = []
    for line in text.splitlines():
        if _TABLE_SEPARATOR.match(line) and "|" in line:
            continue
        heading = _HEADING.match(line)
        if heading:
            title = heading.group(1).strip().rstrip("#").strip()
            line = f"*{title}*" if title else ""
        elif "|" in line and line.strip().startswith("|"):
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            line = " · ".join(cell for cell in cells if cell)
        else:
            line = _BULLET.sub(r"\1- ", line)
        lines.append(line)
    result = "\n".join(lines)
    result = _BOLD.sub(r"*\1*", result)
    result = _BOLD_ALT.sub(r"_\1_", result)
    result = _STRIKE.sub(r"~\1~", result)
    result = _LINK.sub(lambda m: m.group(2) if m.group(1).strip() == m.group(2) else f"{m.group(1)} ({m.group(2)})", result)
    return result


_DIRECTIVE = re.compile(r"^\s*\[(react|quote)\s*:\s*([^\]\n]{1,16})\][ \t]*\n?", re.IGNORECASE)
_ALNUM = re.compile(r"[0-9A-Za-z]")


def parse_reply_directives(text: str) -> tuple[str, str | None, int | None]:
    """Split the agent's optional leading gesture directives from its reply.

    Returns ``(clean_text, reaction_emoji, quote_index)``. Directives are only
    honored at the very start of the reply; anything malformed is dropped so a
    hallucinated directive can never leak to the customer."""
    emoji: str | None = None
    quote: int | None = None
    remaining = text or ""
    while True:
        match = _DIRECTIVE.match(remaining)
        if not match:
            break
        kind, value = match.group(1).lower(), match.group(2).strip()
        if kind == "react" and emoji is None and value and len(value) <= 8 and not _ALNUM.search(value):
            emoji = value
        elif kind == "quote" and quote is None and value.isdigit():
            quote = int(value)
        remaining = remaining[match.end():]
    return remaining.strip(), emoji, quote
