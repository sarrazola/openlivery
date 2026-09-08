/**
 * Talks to the server this session was opened against.
 *
 * The server is not baked in: a person signs in by typing the address of the
 * instance their agency runs, so every call takes the base URL from the stored
 * session. Sign-in resolves the portal from the credentials and returns a token
 * that is sent as a bearer credential from then on, because a native client
 * cannot rely on cookies surviving a restart.
 */

import { strings } from "./i18n";
import { privacyStrings } from "./privacyStrings";

const sessionAccess = new Map<string, boolean>();

/** The app closes this gate while permission or session refresh is pending. */
export function setSessionAccess(session: Session, allowed: boolean): void {
  sessionAccess.set(session.token, allowed);
}

function requireSessionAccess(token?: string): void {
  if (token && sessionAccess.get(token) === false) throw new ApiError(privacyStrings().permissionRequired, 428);
}

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
  privacy?: PrivacyDisclosure;
};

export type PrivacyDisclosure = {
  version: string;
  destinations: { kind: "ai" | "integration" | "notification"; name: string; host: string; capabilities: string[] }[];
};

export type Attachment = {
  id: string;
  kind: string;
  mime: string;
  filename: string | null;
  size_bytes: number;
};

export type ConversationMode = "ai" | "human";
export type ConversationStatus = "open" | "resolved";
export type Availability = "online" | "away";
export type ChannelCapabilities = Partial<Record<"text" | "image" | "audio" | "video" | "file" | "quotes" | "reactions" | "templates", boolean>>;

export type Message = {
  id: string;
  role: "user" | "assistant" | "system";
  kind: "message" | "activity";
  activity: ({ event: string } & Record<string, unknown>) | null;
  content: string;
  sender_type: string;
  sender_name: string | null;
  external_message_id: string | null;
  delivery_status: string | null;
  delivery_error: string | null;
  reaction: string | null;
  incoming_reaction: string | null;
  quoted_message_id: string | null;
  created_at: string;
  attachments: Attachment[];
};

export type Conversation = {
  id: string;
  client_id: string;
  agent_id: string;
  title: string;
  mode: ConversationMode;
  status: ConversationStatus;
  channel: string;
  external_chat_id: string | null;
  contact_name: string | null;
  contact_id: string | null;
  preview: string;
  unread: boolean;
  unread_count: number;
  assignee_id: string | null;
  assignee_name: string | null;
  team_id: string | null;
  team_name: string | null;
  reply_window_until: string | null;
  reply_window_open: boolean;
  human_reply_window_open?: boolean;
  human_reply_window_until?: string | null;
  reply_block_reason?: string | null;
  social_channel_id?: string | null;
  channel_capabilities?: ChannelCapabilities;
  last_inbound_at: string | null;
  resolved_at: string | null;
  first_reply_at: string | null;
  taken_over_at: string | null;
  waiting_since: string | null;
  created_at: string;
  updated_at: string;
};

export type ConversationDetail = Conversation & { messages: Message[] };
export type InboxSummary = {
  open: number;
  resolved: number;
  human: number;
  ai: number;
  unread: number;
  mine: number;
  unassigned: number;
};
export type PageOptions = { limit?: number; offset?: number; search?: string; signal?: AbortSignal };
export type ConversationFilters = PageOptions & {
  status?: ConversationStatus;
  mode?: ConversationMode;
  assignee?: "me" | "none";
  team?: string;
  unread?: boolean;
  channel?: string;
};
export type PortalMember = { id: string; name: string; email: string; availability: Availability };
export type Team = {
  id: string;
  name: string;
  description: string;
  strategy: "round_robin" | "least_busy";
  channels: string[];
  is_default: boolean;
  members: PortalMember[];
  open_count: number;
  unassigned_count: number;
};
export type TeamUpdate = {
  name: string;
  description: string;
  strategy: Team["strategy"];
  channels: string[];
  is_default: boolean;
  member_ids: string[];
};
export type PortalReport = {
  started: number;
  resolved: number;
  open_now: number;
  inbound_messages: number;
  human_replies: number;
  ai_replies: number;
  active_contacts: number;
  agents_online: number;
  avg_first_reply_seconds: number | null;
  avg_resolution_seconds: number | null;
  by_day: { date: string; started: number; resolved: number }[];
  by_channel: { channel: string; started: number }[];
  by_agent: { name: string; availability: string; replies: number; assigned: number; open_now: number }[];
};
export type ReportFilters = { from: string; to: string; tz_offset: number; channel?: string; assignee_id?: string; team_id?: string; signal?: AbortSignal };
export type PortalChannel = {
  channel: string;
  status: string;
  phone_number: string | null;
  display_name: string | null;
  supports_templates: boolean;
  id?: string;
  provider?: string;
  external_account_id?: string | null;
  username?: string | null;
  capabilities?: ChannelCapabilities;
};
export type Template = {
  id: string | null;
  name: string;
  language: string;
  category: string;
  status: string;
  body: string;
  footer: string;
  variables: number;
  rejected_reason: string | null;
};
export type TemplateSend = { name: string; language: string; variables: string[] };
export type CannedReply = { id: string; shortcut: string; content: string; updated_at: string };
export type Contact = {
  id: string;
  name: string;
  phone: string | null;
  email: string | null;
  notes: string;
  created_at: string;
  updated_at: string;
  conversation_count: number;
  open_count: number;
  last_activity_at: string | null;
};
export type ContactCreate = { name?: string; phone: string; email?: string | null; notes?: string };
export type ContactUpdate = { name?: string; phone?: string; email?: string | null; notes?: string };
export type ConversationStart =
  | { channel: "whatsapp"; text: string }
  | { channel: "whatsapp_cloud"; template: TemplateSend };

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

/** API failures are parsed once for JSON replies and multipart uploads alike. */
async function responseBody<T>(response: Response, fallback = strings().errors.generic): Promise<T> {
  if (!response.ok) {
    let message = fallback;
    try {
      const body = await response.json();
      if (typeof body.detail === "string") message = body.detail;
      else if (Array.isArray(body.detail) && typeof body.detail[0]?.msg === "string") message = body.detail[0].msg;
    } catch { /* Gateways may return HTML instead of an API error. */ }
    throw new ApiError(message, response.status);
  }
  if (response.status === 204) return undefined as T;
  try {
    return await response.json() as T;
  } catch {
    throw new ApiError(fallback, response.status);
  }
}

async function request<T>(server: string, path: string, init: RequestInit = {}, token?: string): Promise<T> {
  if (path !== "/mobile/session" && !(path.startsWith("/mobile/devices/") && init.method === "DELETE")) requireSessionAccess(token);
  const controller = new AbortController();
  const cancel = () => controller.abort();
  if (init.signal?.aborted) controller.abort();
  init.signal?.addEventListener("abort", cancel, { once: true });
  const timeout = setTimeout(cancel, 30_000);
  try {
    const headers = new Headers(init.headers);
    if (init.body) headers.set("Content-Type", "application/json");
    if (token) headers.set("Authorization", `Bearer ${token}`);
    const response = await fetch(`${server}/api${path}`, {
      ...init,
      signal: controller.signal,
      // Native and browser previews must use this session's bearer identity.
      credentials: "omit",
      headers,
    });
    return await responseBody<T>(response);
  } catch (error) {
    if (error instanceof ApiError || init.signal?.aborted) throw error;
    throw new ApiError(strings().errors.unreachable, 0);
  } finally {
    clearTimeout(timeout);
    init.signal?.removeEventListener("abort", cancel);
  }
}

function portalPath(session: Session, path: string): string {
  requireSessionAccess(session.token);
  return `/portal/${encodeURIComponent(session.portal_slug)}${path}`;
}

/** Only advertised filters are sent; the server owns unread and assignment semantics. */
export function conversationQuery(options: ConversationFilters = {}): string {
  const params = new URLSearchParams();
  for (const key of ["status", "mode", "assignee", "team", "channel"] as const) {
    if (options[key]) params.set(key, options[key]);
  }
  if (options.search?.trim()) params.set("search", options.search.trim());
  if (options.unread) params.set("unread", "true");
  if (options.limit !== undefined) params.set("limit", String(Math.min(200, Math.max(1, Math.trunc(options.limit) || 1))));
  if (options.offset !== undefined) params.set("offset", String(Math.max(0, Math.trunc(options.offset) || 0)));
  const query = params.toString();
  return query ? `?${query}` : "";
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

export function listConversations(server: string, session: Session, options: ConversationFilters = {}): Promise<Conversation[]> {
  return request(server, portalPath(session, `/conversations${conversationQuery(options)}`), { signal: options.signal }, session.token);
}

export function getInboxSummary(server: string, session: Session): Promise<InboxSummary> {
  return request(server, portalPath(session, "/conversations/summary"), {}, session.token);
}

export function getConversation(server: string, session: Session, id: string): Promise<ConversationDetail> {
  return request(server, portalPath(session, `/conversations/${encodeURIComponent(id)}`), {}, session.token);
}

function changeConversation(server: string, session: Session, id: string, action: string, method: string, body: unknown): Promise<ConversationDetail> {
  return request(server, portalPath(session, `/conversations/${encodeURIComponent(id)}/${action}`), { method, body: JSON.stringify(body) }, session.token);
}

export function setMode(server: string, session: Session, id: string, mode: ConversationMode): Promise<ConversationDetail> {
  return changeConversation(server, session, id, "mode", "PATCH", { mode });
}

/** Resolved cases are final. New customer messages create another case. */
export function setStatus(server: string, session: Session, id: string, status: "resolved"): Promise<ConversationDetail> {
  return changeConversation(server, session, id, "status", "PATCH", { status });
}

export function assignConversation(server: string, session: Session, id: string, assigneeId: string): Promise<ConversationDetail> {
  return changeConversation(server, session, id, "assignment", "POST", { assignee_id: assigneeId });
}

export function setConversationTeam(server: string, session: Session, id: string, teamId: string | null): Promise<ConversationDetail> {
  return changeConversation(server, session, id, "team", "PATCH", { team_id: teamId });
}

export function markRead(server: string, session: Session, id: string): Promise<void> {
  return request(server, portalPath(session, `/conversations/${encodeURIComponent(id)}/read`), { method: "POST" }, session.token);
}

export function reply(server: string, session: Session, id: string, content: string, quotedMessageId: string | null = null): Promise<ConversationDetail> {
  return changeConversation(server, session, id, "reply", "POST", { content, quoted_message_id: quotedMessageId });
}

export function reactToMessage(server: string, session: Session, id: string, messageId: string, emoji: string): Promise<ConversationDetail> {
  return changeConversation(server, session, id, `messages/${encodeURIComponent(messageId)}/reaction`, "POST", { emoji });
}

export function listMembers(server: string, session: Session): Promise<PortalMember[]> {
  return request(server, portalPath(session, "/members"), {}, session.token);
}

export function listTeams(server: string, session: Session): Promise<Team[]> {
  return request(server, portalPath(session, "/teams"), {}, session.token);
}

export function createTeam(server: string, session: Session, team: TeamUpdate): Promise<Team> {
  return request(server, portalPath(session, "/teams"), { method: "POST", body: JSON.stringify(team) }, session.token);
}

export function updateTeam(server: string, session: Session, id: string, team: TeamUpdate): Promise<Team> {
  return request(server, portalPath(session, `/teams/${encodeURIComponent(id)}`), { method: "PATCH", body: JSON.stringify(team) }, session.token);
}

export function getReport(server: string, session: Session, filters: ReportFilters): Promise<PortalReport> {
  const params = new URLSearchParams({ from: filters.from, to: filters.to, tz_offset: String(filters.tz_offset) });
  for (const key of ["channel", "assignee_id", "team_id"] as const) if (filters[key]) params.set(key, filters[key]);
  return request(server, portalPath(session, `/reports?${params}`), { signal: filters.signal }, session.token);
}

export function setAvailability(server: string, session: Session, availability: Availability): Promise<PortalMember> {
  return request(server, portalPath(session, "/me"), { method: "PATCH", body: JSON.stringify({ availability }) }, session.token);
}

export function listChannels(server: string, session: Session): Promise<PortalChannel[]> {
  return request(server, portalPath(session, "/channels"), {}, session.token);
}

export function listTemplates(server: string, session: Session): Promise<Template[]> {
  return request(server, portalPath(session, "/templates"), {}, session.token);
}

export function replyWithTemplate(server: string, session: Session, id: string, template: TemplateSend): Promise<ConversationDetail> {
  return changeConversation(server, session, id, "reply-template", "POST", template);
}

export function listCannedReplies(server: string, session: Session): Promise<CannedReply[]> {
  return request(server, portalPath(session, "/canned-responses"), {}, session.token);
}

export function listContacts(server: string, session: Session, options: PageOptions = {}): Promise<Contact[]> {
  return request(server, portalPath(session, `/contacts${conversationQuery(options)}`), { signal: options.signal }, session.token);
}

export function getContact(server: string, session: Session, id: string): Promise<Contact> {
  return request(server, portalPath(session, `/contacts/${encodeURIComponent(id)}`), {}, session.token);
}

export function createContact(server: string, session: Session, contact: ContactCreate): Promise<Contact> {
  return request(server, portalPath(session, "/contacts"), { method: "POST", body: JSON.stringify(contact) }, session.token);
}

export function updateContact(server: string, session: Session, id: string, contact: ContactUpdate): Promise<Contact> {
  return request(server, portalPath(session, `/contacts/${encodeURIComponent(id)}`), { method: "PATCH", body: JSON.stringify(contact) }, session.token);
}

export function listContactConversations(server: string, session: Session, id: string): Promise<Conversation[]> {
  return request(server, portalPath(session, `/contacts/${encodeURIComponent(id)}/conversations`), {}, session.token);
}

export function startConversation(server: string, session: Session, contactId: string, payload: ConversationStart): Promise<ConversationDetail> {
  return request(server, portalPath(session, `/contacts/${encodeURIComponent(contactId)}/conversations`), { method: "POST", body: JSON.stringify(payload) }, session.token);
}

/**
 * Send a file into a conversation: a photo, a voice note, anything.
 *
 * Multipart rather than JSON, because the server's portal endpoint is the same
 * one the browser posts to - the app is a second client of it, not a second
 * implementation.
 *
 * The body is a real Blob. React Native historically let you append
 * {uri, name, type} instead, but the fetch this app runs on is spec-compliant
 * and rejects that with "Unsupported FormDataPart implementation"; expo-file-
 * system's File is a Blob over a local path, so nothing is read into memory to
 * satisfy it. Content-Type is left for fetch, which is the only thing that
 * knows the multipart boundary.
 */
export async function replyWithFile(
  server: string,
  session: Session,
  id: string,
  file: { uri: string; name: string; type: string },
  caption = "",
): Promise<ConversationDetail> {
  requireSessionAccess(session.token);
  // Imported here rather than at the top so this module stays loadable outside
  // a React Native runtime - scripts/verify-flow.ts exercises the rest of it
  // from plain Node.
  const { File } = await import("expo-file-system");
  const body = new FormData();
  body.append("file", new File(file.uri), file.name);
  body.append("caption", caption);
  let response: Response;
  try {
    response = await fetch(
      `${server}/api${portalPath(session, `/conversations/${encodeURIComponent(id)}/reply-media`)}`,
      { method: "POST", body, credentials: "omit", headers: authHeaders(session) },
    );
  } catch (cause) {
    // Keep the underlying reason: an upload that never leaves the phone and one
    // that cannot reach the server look identical without it.
    const detail = cause instanceof Error ? cause.message : String(cause);
    throw new ApiError(`${strings().errors.sendFile}: ${detail}`, 0);
  }
  return responseBody<ConversationDetail>(response, strings().errors.sendFile);
}

/** Where an attachment can be fetched from, with the session's credentials. */
export function attachmentUrl(server: string, session: Session, conversationId: string, attachmentId: string): string {
  return `${server}/api${portalPath(session, `/conversations/${encodeURIComponent(conversationId)}/attachments/${encodeURIComponent(attachmentId)}`)}`;
}

/**
 * Attachments are behind the session, so they cannot be plain <Image src>.
 * Everything that renders one needs this header.
 */
export function authHeaders(session: Session): Record<string, string> {
  requireSessionAccess(session.token);
  return { Authorization: `Bearer ${session.token}` };
}

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
