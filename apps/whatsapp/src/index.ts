import { createServer, type IncomingMessage, type ServerResponse } from "node:http";
import { loadEnvFile } from "node:process";
import { resolve } from "node:path";

try { loadEnvFile(resolve(process.cwd(), "../.env")); } catch {}

const [{ bridgeToken }, manager] = await Promise.all([
  import("./api.js"),
  import("./manager.js"),
]);

const port = Number(process.env.WHATSAPP_BRIDGE_PORT || 3101);
const host = process.env.WHATSAPP_BRIDGE_HOST || "127.0.0.1";

function json(response: ServerResponse, status: number, body?: unknown): void {
  response.statusCode = status;
  response.setHeader("Content-Type", "application/json; charset=utf-8");
  response.end(body === undefined ? undefined : JSON.stringify(body));
}

async function body(request: IncomingMessage, maxBytes = 100_000): Promise<Record<string, unknown>> {
  const chunks: Buffer[] = [];
  let length = 0;
  for await (const chunk of request) {
    const part = Buffer.from(chunk);
    length += part.length;
    if (length > maxBytes) throw new Error("Request too large");
    chunks.push(part);
  }
  if (!chunks.length) return {};
  return JSON.parse(Buffer.concat(chunks).toString("utf8")) as Record<string, unknown>;
}

// Outbound media arrives base64-encoded; the backend caps files at 20 MB.
const MAX_SEND_BYTES = 30_000_000;

const server = createServer(async (request, response) => {
  try {
    const url = new URL(request.url || "/", `http://${request.headers.host || "localhost"}`);
    if (request.method === "GET" && url.pathname === "/health") return json(response, 200, { status: "ok" });
    if (request.headers["x-bridge-token"] !== bridgeToken) return json(response, 401, { error: "Invalid internal token" });
    const match = url.pathname.match(/^\/channels\/([0-9a-f-]+)\/(connect|disconnect|send)$/i);
    if (!match) return json(response, 404, { error: "Route not found" });
    const channelId = match[1]!;
    const action = match[2]!;
    if (request.method !== "POST") return json(response, 405, { error: "Method not allowed" });
    if (action === "connect") {
      await manager.connectChannel(channelId);
      return json(response, 202, { ok: true });
    }
    if (action === "disconnect") {
      await manager.disconnectChannel(channelId);
      return json(response, 200, { ok: true });
    }
    const payload = await body(request, MAX_SEND_BYTES);
    const text = typeof payload.text === "string" ? payload.text.trim() : "";
    const hasMedia = typeof payload.media_base64 === "string" && payload.media_base64.length > 0;
    if (typeof payload.remote_jid !== "string" || (!text && !hasMedia)) {
      return json(response, 400, { error: "Invalid destination or message" });
    }
    const media = hasMedia
      ? {
          kind: (payload.media_kind === "image" || payload.media_kind === "audio" || payload.media_kind === "video" ? payload.media_kind : "file") as "image" | "audio" | "video" | "file",
          base64: payload.media_base64 as string,
          mime: typeof payload.media_mime === "string" && payload.media_mime ? payload.media_mime : "application/octet-stream",
          filename: typeof payload.filename === "string" ? payload.filename : null,
          seconds: typeof payload.media_seconds === "number" && payload.media_seconds > 0 ? Math.round(payload.media_seconds) : null,
        }
      : undefined;
    const externalMessageId = await manager.sendMessage(channelId, payload.remote_jid, text, media);
    return json(response, 200, { external_message_id: externalMessageId });
  } catch (error) {
    console.error("[WhatsApp] Operation error:", (error as Error).message);
    return json(response, 500, { error: (error as Error).message });
  }
});

server.listen(port, host, () => {
  console.log(`[WhatsApp] Bridge ready at ${host}:${port}`);
  void manager.restoreChannels().catch((error) => console.error("[WhatsApp] Could not restore sessions:", error.message));
});

async function stop(): Promise<void> {
  await manager.shutdown();
  server.close(() => process.exit(0));
}

process.on("SIGINT", () => void stop());
process.on("SIGTERM", () => void stop());
