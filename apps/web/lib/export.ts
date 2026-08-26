import type { Attachment } from "@/types";

type ExportMessage = {
  role: string;
  content: string;
  created_at?: string | null;
  sender_name?: string | null;
  attachments?: Attachment[];
};

function attachmentLabel(attachment: Attachment): string {
  if (attachment.kind === "image") return "[image]";
  if (attachment.kind === "audio") return "[voice note]";
  if (attachment.kind === "video") return "[video]";
  return `[file: ${attachment.filename || "attachment"}]`;
}

function stamp(iso?: string | null): string {
  const date = iso ? new Date(iso) : new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

/** Build a plain-text transcript from a list of messages. */
export function chatToText(
  messages: ExportMessage[],
  opts: { title: string; channel?: string; agentLabel?: string; visitorLabel?: string },
): string {
  const lines: string[] = [opts.title];
  if (opts.channel) lines.push(`Channel: ${opts.channel}`);
  lines.push(`Exported: ${stamp()}`, "");
  for (const message of messages) {
    const who = message.sender_name
      || (message.role === "assistant" ? opts.agentLabel || "Agent" : opts.visitorLabel || "Visitor");
    const parts = (message.attachments ?? []).map(attachmentLabel);
    if (message.content) parts.push(message.content);
    lines.push(`[${stamp(message.created_at)}] ${who}: ${parts.join(" ")}`.trimEnd());
  }
  return lines.join("\n");
}

/** Trigger a browser download of a text file. */
export function downloadText(text: string, title: string): void {
  const safe = (title || "conversation").replace(/[^\w.-]+/g, "_").slice(0, 60);
  const blob = new Blob([text], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `${safe}.txt`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 0);
}
