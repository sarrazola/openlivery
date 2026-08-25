import { extractMessageContent, type WAMessage } from "@whiskeysockets/baileys";

export function incomingText(message: WAMessage): string | null {
  const content = extractMessageContent(message.message);
  if (!content) return null;
  const text =
    content.conversation ||
    content.extendedTextMessage?.text ||
    content.imageMessage?.caption ||
    content.videoMessage?.caption ||
    content.buttonsResponseMessage?.selectedDisplayText ||
    content.listResponseMessage?.title ||
    content.templateButtonReplyMessage?.selectedDisplayText;
  return text?.trim() || null;
}

export type IncomingMedia = { kind: "image" | "audio" | "video"; mimetype: string };

export function incomingMedia(message: WAMessage): IncomingMedia | null {
  const content = extractMessageContent(message.message);
  if (!content) return null;
  if (content.imageMessage) return { kind: "image", mimetype: content.imageMessage.mimetype || "image/jpeg" };
  if (content.audioMessage) return { kind: "audio", mimetype: content.audioMessage.mimetype || "audio/ogg" };
  if (content.videoMessage) return { kind: "video", mimetype: content.videoMessage.mimetype || "video/mp4" };
  return null;
}

export function isDirectIncoming(message: WAMessage): boolean {
  const jid = message.key.remoteJid;
  return Boolean(
    jid &&
    message.key.id &&
    !message.key.fromMe &&
    !jid.endsWith("@g.us") &&
    jid !== "status@broadcast" &&
    !jid.endsWith("@newsletter"),
  );
}
