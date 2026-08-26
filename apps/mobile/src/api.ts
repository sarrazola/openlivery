/**
 * Talks to an OpenLivery server.
 *
 * The server is not baked in: a person signs in by typing the address of the
 * instance their agency runs, so every call takes the base URL from the stored
 * session. Sign-in resolves the portal from the credentials and returns a token
 * that is sent as a bearer credential from then on, because a native client
 * cannot rely on cookies surviving a restart.
 */

export type Branding = {
  agency_name: string;
  client_name: string;
  portal_title: string;
  brand_color: string;
  agency_logo_url: string | null;
  client_logo_url: string | null;
};

/**
 * How the server this app is pointed at expects to be able to notify it.
 *
 * The app deliberately does not decide this. One build has to work against a
 * self-hosted server that sends nothing and a hosted one that does, and a phone
 * that subscribes to a push service nobody asked for costs whoever owns that
 * service money. So the server says, and "none" means do not initialise
 * anything at all.
 */
export type PushConfig = {
  enabled: boolean;
  provider: string;
};

export type Session = {
  token: string;
  portal_slug: string;
  client_id: string;
  user_id: string | null;
  user_name: string;
  branding: Branding;
  push: PushConfig;
  api_version: number;
};

export type Attachment = {
  id: string;
  kind: string;
  mime: string;
  filename: string | null;
  size_bytes: number;
};

export type Message = {
  id: string;
  role: "user" | "assistant";
  content: string;
  sender_type?: string | null;
  sender_name?: string | null;
  created_at: string;
  attachments?: Attachment[];
};

export type Conversation = {
  id: string;
  title: string;
  mode: "ai" | "human";
  channel: string;
  contact_name: string | null;
  preview: string | null;
  updated_at: string;
};

export type ConversationDetail = Conversation & { messages: Message[] };

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

/** Accepts what a person actually types: "10.0.0.4:8000", "example.com", a full URL. */
export function normalizeServerUrl(input: string): string {
  let value = (input || "").trim().replace(/\/+$/, "");
  if (!value) return "";
  if (!/^https?:\/\//i.test(value)) {
    const isLocal = /^(localhost|127\.0\.0\.1|10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.)/i.test(value);
    value = `${isLocal ? "http" : "https"}://${value}`;
  }
  return value.replace(/\/api$/, "");
}

async function request<T>(server: string, path: string, init: RequestInit = {}, token?: string): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${server}/api${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(init.headers || {}),
      },
    });
  } catch {
    // fetch only rejects when the request never completed: wrong address, no
    // route to the host, TLS refused. Worth its own message, because the usual
    // cause is a typo in the server field.
    throw new ApiError("Could not reach that server. Check the address and that you are on the same network.", 0);
  }
  if (!response.ok) {
    let message = "Something went wrong";
    try {
      const body = await response.json();
      if (typeof body.detail === "string") message = body.detail;
      else if (Array.isArray(body.detail) && body.detail[0]?.msg) message = body.detail[0].msg;
    } catch {}
    throw new ApiError(message, response.status);
  }
  if (response.status === 204) return undefined as T;
  return response.json();
}

export function signIn(server: string, email: string, password: string): Promise<Session> {
  return request<Session>(server, "/mobile/sign-in", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

/** Re-checks a stored token on launch and refreshes branding the agency may have changed. */
export function resumeSession(server: string, token: string): Promise<Session> {
  return request<Session>(server, "/mobile/session", {}, token);
}

export function listConversations(server: string, session: Session): Promise<Conversation[]> {
  return request<Conversation[]>(server, `/portal/${session.portal_slug}/conversations`, {}, session.token);
}

export function getConversation(server: string, session: Session, id: string): Promise<ConversationDetail> {
  return request<ConversationDetail>(server, `/portal/${session.portal_slug}/conversations/${id}`, {}, session.token);
}

export function setMode(server: string, session: Session, id: string, mode: "ai" | "human"): Promise<ConversationDetail> {
  return request<ConversationDetail>(
    server,
    `/portal/${session.portal_slug}/conversations/${id}/mode`,
    { method: "PATCH", body: JSON.stringify({ mode }) },
    session.token,
  );
}

export function reply(server: string, session: Session, id: string, content: string): Promise<ConversationDetail> {
  return request<ConversationDetail>(
    server,
    `/portal/${session.portal_slug}/conversations/${id}/reply`,
    { method: "POST", body: JSON.stringify({ content }) },
    session.token,
  );
}

/** Absolute URL for an image the API returns as a path, e.g. a logo. */
/** Tell the server where to reach this install. */
export function registerDevice(
  server: string,
  session: Session,
  device: { token: string; provider: string; platform: string },
): Promise<{ registered: boolean; provider: string }> {
  return request(server, "/mobile/devices", { method: "POST", body: JSON.stringify(device) }, session.token);
}

/** Stop notifying this install, on sign-out. */
export async function forgetDevice(server: string, session: Session, token: string): Promise<void> {
  await request(
    server,
    `/mobile/devices/${encodeURIComponent(token)}`,
    { method: "DELETE" },
    session.token,
  );
}

export function assetUrl(server: string, path: string | null): string | null {
  if (!path) return null;
  return path.startsWith("http") ? path : `${server}${path}`;
}
