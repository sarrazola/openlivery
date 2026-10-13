// Web push for the portal: the browser's own protocol, no vendor script.
//
// The server publishes a public key (GET /portal/{slug}/push); the browser
// subscribes with it through the service worker in /push-worker.js and the
// subscription is registered against the person signed in. Every portal load
// registers again so the row follows whoever is in front of the browser.

import { api } from "@/lib/api";

export type WebPushConfig = { enabled: boolean; public_key: string };
export type PushState = "unsupported" | "unavailable" | "denied" | "off" | "on";

const WORKER_URL = "/push-worker.js";

export function pushSupported(): boolean {
  return typeof window !== "undefined" && "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
}

function keyBytes(base64url: string): Uint8Array {
  const padded = base64url + "=".repeat((4 - (base64url.length % 4)) % 4);
  const raw = atob(padded.replace(/-/g, "+").replace(/_/g, "/"));
  const bytes = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i += 1) bytes[i] = raw.charCodeAt(i);
  return bytes;
}

async function registration(): Promise<ServiceWorkerRegistration> {
  const existing = await navigator.serviceWorker.getRegistration(WORKER_URL);
  if (existing) return existing;
  return navigator.serviceWorker.register(WORKER_URL, { scope: "/" });
}

export async function currentSubscription(): Promise<PushSubscription | null> {
  if (!pushSupported()) return null;
  try {
    const existing = await navigator.serviceWorker.getRegistration(WORKER_URL);
    return existing ? await existing.pushManager.getSubscription() : null;
  } catch {
    return null;
  }
}

export async function pushConfig(slug: string): Promise<WebPushConfig> {
  try {
    return await api<WebPushConfig>(`/portal/${slug}/push`);
  } catch {
    return { enabled: false, public_key: "" };
  }
}

/** Where this browser stands, for the settings toggle. */
export async function pushState(slug: string, config?: WebPushConfig): Promise<PushState> {
  if (!pushSupported()) return "unsupported";
  const current = config ?? (await pushConfig(slug));
  if (!current.enabled) return "unavailable";
  if (Notification.permission === "denied") return "denied";
  return (await currentSubscription()) ? "on" : "off";
}

async function register(slug: string, subscription: PushSubscription): Promise<void> {
  const json = subscription.toJSON();
  await api(`/portal/${slug}/push/subscriptions`, {
    method: "POST",
    body: JSON.stringify({ endpoint: json.endpoint, keys: json.keys }),
  });
}

/** Ask permission if needed, subscribe, and register for the person signed in. */
export async function enablePush(slug: string, config?: WebPushConfig): Promise<PushState> {
  if (!pushSupported()) return "unsupported";
  const current = config ?? (await pushConfig(slug));
  if (!current.enabled || !current.public_key) return "unavailable";
  const permission = await Notification.requestPermission();
  if (permission !== "granted") return permission === "denied" ? "denied" : "off";
  const worker = await registration();
  await navigator.serviceWorker.ready;
  const subscription =
    (await worker.pushManager.getSubscription()) ??
    (await worker.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: keyBytes(current.public_key) as BufferSource }));
  await register(slug, subscription);
  return "on";
}

/** Forget this browser on the server and let the subscription go. */
export async function disablePush(slug: string): Promise<PushState> {
  const subscription = await currentSubscription();
  if (!subscription) return "off";
  try {
    await api(`/portal/${slug}/push/subscriptions`, { method: "DELETE", body: JSON.stringify({ endpoint: subscription.endpoint }) });
  } catch {
    // The server row dies on its own the next time delivery fails.
  }
  try {
    await subscription.unsubscribe();
  } catch {
    /* already gone */
  }
  return "off";
}

/** On every portal load: re-register an existing subscription so it belongs to
 * whoever is signed in now. Returns whether this browser is subscribed. */
export async function syncPush(slug: string): Promise<boolean> {
  const subscription = await currentSubscription();
  if (!subscription) return false;
  try {
    await register(slug, subscription);
  } catch {
    /* offline or signed out: the next load retries */
  }
  return true;
}

export type WorkerMessage =
  | { type: "push"; payload: { title: string; body: string; data: Record<string, string> } }
  | { type: "open"; data: Record<string, string> };

/** Listen to the worker (a push while the portal is visible, a notification click). */
export function onWorkerMessage(handler: (message: WorkerMessage) => void): () => void {
  if (!pushSupported()) return () => {};
  const listener = (event: MessageEvent) => {
    const message = event.data as WorkerMessage | undefined;
    if (message && (message.type === "push" || message.type === "open")) handler(message);
  };
  navigator.serviceWorker.addEventListener("message", listener);
  return () => navigator.serviceWorker.removeEventListener("message", listener);
}
