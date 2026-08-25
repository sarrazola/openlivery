import makeWASocket, {
  Browsers,
  DisconnectReason,
  downloadMediaMessage,
  type WASocket,
  type WAMessage,
} from "@whiskeysockets/baileys";
import pino from "pino";
import QRCode from "qrcode";
import { backend, setStatus } from "./api.js";
import { createDatabaseAuth } from "./auth.js";
import { incomingMedia, incomingText, isDirectIncoming } from "./messages.js";

// Skip forwarding media larger than this; the backend also caps at 20 MB.
const MAX_MEDIA_BYTES = 18 * 1024 * 1024;

type ChannelConfig = {
  id: string;
  client_id: string;
  agent_id: string;
  enabled: boolean;
  auth_state: unknown | null;
};

type ChannelRuntime = {
  socket: WASocket;
  stopRequested: boolean;
  reconnectTimer?: NodeJS.Timeout;
};

type InboundResult = {
  accepted: boolean;
  reply?: string | null;
  outbound_message_id?: string | null;
};

const logger = pino({ level: process.env.WHATSAPP_LOG_LEVEL || "silent" });
const runtimes = new Map<string, ChannelRuntime>();

function errorCode(error: unknown): number | undefined {
  return (error as { output?: { statusCode?: number } } | undefined)?.output?.statusCode;
}

function cleanNumber(jid?: string | null): string | null {
  if (!jid) return null;
  return jid.split(":")[0]?.split("@")[0] || null;
}

async function processIncoming(channelId: string, socket: WASocket, message: WAMessage): Promise<void> {
  if (!isDirectIncoming(message)) return;
  const text = incomingText(message);
  const media = incomingMedia(message);
  const remoteJid = message.key.remoteJid;
  const externalMessageId = message.key.id;
  if ((!text && !media) || !remoteJid || !externalMessageId) return;

  const body: Record<string, unknown> = {
    external_message_id: externalMessageId,
    remote_jid: remoteJid,
    sender_name: message.pushName || null,
    text: text || "",
  };
  if (media) {
    try {
      const buffer = (await downloadMediaMessage(
        message,
        "buffer",
        {},
        { logger, reuploadRequest: socket.updateMediaMessage },
      )) as Buffer;
      if (buffer.length <= MAX_MEDIA_BYTES) {
        body.media_kind = media.kind;
        body.media_mime = media.mimetype;
        body.media_base64 = buffer.toString("base64");
      }
    } catch (error) {
      console.error(`[WhatsApp ${channelId}] Could not download media:`, (error as Error).message);
    }
  }

  const result = await backend<InboundResult>(`/channels/${channelId}/inbound`, {
    method: "POST",
    body: JSON.stringify(body),
  });
  if (!result.reply) return;
  const sent = await socket.sendMessage(remoteJid, { text: result.reply });
  if (result.outbound_message_id && sent?.key.id) {
    await backend(`/channels/${channelId}/outbound-confirm`, {
      method: "POST",
      body: JSON.stringify({
        message_id: result.outbound_message_id,
        external_message_id: sent.key.id,
      }),
    });
  }
}

export async function connectChannel(channelId: string): Promise<void> {
  const current = runtimes.get(channelId);
  if (current && !current.stopRequested) return;
  const config = await backend<ChannelConfig>(`/channels/${channelId}`);
  if (!config.enabled) throw new Error("The channel is disabled");
  await setStatus(channelId, config.auth_state ? "reconnecting" : "connecting");

  const { state, persist } = createDatabaseAuth(channelId, config.auth_state || undefined);
  const socket = makeWASocket({
    auth: state,
    logger,
    browser: Browsers.macOS("OpenLivery"),
    syncFullHistory: false,
    shouldSyncHistoryMessage: () => false,
    markOnlineOnConnect: false,
    generateHighQualityLinkPreview: false,
  });
  const runtime: ChannelRuntime = { socket, stopRequested: false };
  runtimes.set(channelId, runtime);

  socket.ev.on("creds.update", async (update) => {
    Object.assign(state.creds, update);
    try { await persist(); } catch (error) { console.error(`[WhatsApp ${channelId}] Could not save the session:`, (error as Error).message); }
  });

  socket.ev.on("messages.upsert", async ({ messages, type }) => {
    if (type !== "notify") return;
    for (const message of messages) {
      try {
        await processIncoming(channelId, socket, message);
      } catch (error) {
        const detail = `Could not process an incoming message: ${(error as Error).message}`;
        console.error(`[WhatsApp ${channelId}] ${detail}`);
        await setStatus(channelId, "error", { error: detail.slice(0, 500) }).catch(() => undefined);
      }
    }
  });

  socket.ev.on("connection.update", async ({ connection, lastDisconnect, qr }) => {
    try {
      if (qr) {
        const qrCode = await QRCode.toDataURL(qr, { width: 360, margin: 2, errorCorrectionLevel: "M" });
        await setStatus(channelId, "qr", { qr_code: qrCode });
      }
      if (connection === "open") {
        await persist();
        await setStatus(channelId, "connected", {
          phone_number: cleanNumber(socket.user?.id),
          display_name: socket.user?.name || null,
        });
      }
      if (connection === "close") {
        const latest = runtimes.get(channelId);
        if (latest !== runtime) return;
        const code = errorCode(lastDisconnect?.error);
        const loggedOut = code === DisconnectReason.loggedOut || code === DisconnectReason.badSession;
        if (runtime.stopRequested || loggedOut) {
          runtimes.delete(channelId);
          await backend(`/channels/${channelId}/auth`, { method: "DELETE" });
          return;
        }
        await setStatus(channelId, "reconnecting", {
          error: code ? `WhatsApp closed the connection (${code}). Retrying…` : "Connection interrupted. Retrying…",
        });
        runtime.reconnectTimer = setTimeout(() => {
          runtimes.delete(channelId);
          void connectChannel(channelId).catch(async (error) => {
            await setStatus(channelId, "error", { error: (error as Error).message.slice(0, 500) }).catch(() => undefined);
          });
        }, 3000);
      }
    } catch (error) {
      await setStatus(channelId, "error", { error: (error as Error).message.slice(0, 500) }).catch(() => undefined);
    }
  });
}

export async function disconnectChannel(channelId: string): Promise<void> {
  const runtime = runtimes.get(channelId);
  if (runtime) {
    runtime.stopRequested = true;
    if (runtime.reconnectTimer) clearTimeout(runtime.reconnectTimer);
    try { await runtime.socket.logout(); } catch {}
    runtimes.delete(channelId);
  }
  await backend(`/channels/${channelId}/auth`, { method: "DELETE" });
}

export type OutboundMedia = {
  kind: "image" | "audio" | "video" | "file";
  base64: string;
  mime: string;
  filename?: string | null;
  seconds?: number | null;
};

// Flat placeholder waveform: iOS WhatsApp may not render a voice note without one.
const VOICE_WAVEFORM = new Uint8Array(64).fill(24);

export async function sendMessage(
  channelId: string,
  remoteJid: string,
  text: string,
  media?: OutboundMedia,
): Promise<string> {
  const runtime = runtimes.get(channelId);
  if (!runtime || runtime.stopRequested) throw new Error("WhatsApp is not connected")
  let content: Parameters<WASocket["sendMessage"]>[1] = { text };
  if (media) {
    const buffer = Buffer.from(media.base64, "base64");
    if (media.kind === "image") {
      content = { image: buffer, mimetype: media.mime, ...(text ? { caption: text } : {}) };
    } else if (media.kind === "video") {
      content = { video: buffer, mimetype: media.mime, ...(text ? { caption: text } : {}) };
    } else if (media.kind === "audio") {
      const isVoice = media.mime.includes("ogg");
      content = {
        audio: buffer,
        // iOS requires this exact mimetype to play a voice note.
        mimetype: isVoice ? "audio/ogg; codecs=opus" : media.mime,
        ptt: isVoice,
        ...(media.seconds ? { seconds: media.seconds } : {}),
        ...(isVoice ? { waveform: VOICE_WAVEFORM } : {}),
      };
    } else {
      content = {
        document: buffer,
        mimetype: media.mime,
        fileName: media.filename || "file",
        ...(text ? { caption: text } : {}),
      };
    }
  }
  if (media) {
    console.log(
      `[WhatsApp ${channelId}] sending ${media.kind}: mime=${media.mime} bytes=${Buffer.from(media.base64, "base64").length} seconds=${media.seconds ?? "-"}`,
    );
  }
  const sent = await runtime.socket.sendMessage(remoteJid, content);
  if (!sent?.key.id) throw new Error("WhatsApp did not confirm the send")
  // Self-check for voice notes: fetch our own upload back from the WhatsApp CDN
  // the same way a recipient would, so delivery problems show up in the logs.
  if (media?.kind === "audio" && sent.message) {
    try {
      const roundTrip = (await downloadMediaMessage(
        sent,
        "buffer",
        {},
        { logger, reuploadRequest: runtime.socket.updateMediaMessage },
      )) as Buffer;
      console.log(`[WhatsApp ${channelId}] voice self-check OK: ${roundTrip.length} bytes downloadable`);
    } catch (error) {
      console.error(`[WhatsApp ${channelId}] voice self-check FAILED:`, (error as Error).message);
    }
  }
  // Audio messages have no caption on WhatsApp; deliver it as a follow-up text.
  if (media?.kind === "audio" && text) {
    await runtime.socket.sendMessage(remoteJid, { text }).catch(() => undefined);
  }
  return sent.key.id;
}

export async function restoreChannels(): Promise<void> {
  const channels = await backend<Array<{ id: string }>>("/channels");
  const results = await Promise.allSettled(channels.map((item) => connectChannel(item.id)));
  results.forEach((result, index) => {
    if (result.status === "rejected") console.error(`[WhatsApp ${channels[index]?.id}] Could not restore:`, result.reason?.message || result.reason);
  });
}

export async function shutdown(): Promise<void> {
  for (const runtime of runtimes.values()) {
    runtime.stopRequested = true;
    if (runtime.reconnectTimer) clearTimeout(runtime.reconnectTimer);
    runtime.socket.end(new Error("OpenLivery is shutting down"));
  }
  runtimes.clear();
}
