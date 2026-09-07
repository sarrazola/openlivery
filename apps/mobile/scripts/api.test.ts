import assert from "node:assert/strict";
import { afterEach, test } from "node:test";
import {
  ApiError, assignConversation, conversationQuery, getInboxSummary, listContactConversations,
  listConversations, markRead, reactToMessage, reply, replyWithTemplate, setConversationTeam,
  setStatus, updateContact, type Conversation, type Message, type Session,
} from "../src/api";
import {
  canQuoteMessage, canReactToMessage, canReply, conversationTimestamp, inboxFilters,
  interpolateCannedReply, isReplyWindowClosed, mergeConversationPages,
} from "../src/inbox";
import { phoneFrom } from "../src/conversations";

const session = { token: "phone-token", portal_slug: "support" } as Session;
const realFetch = global.fetch;
afterEach(() => { global.fetch = realFetch; });
function capture(body: unknown = {}) {
  const requests: { url: string; init: RequestInit }[] = [];
  global.fetch = async (input, init = {}) => {
    requests.push({ url: String(input), init });
    return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
  };
  return requests;
}
const open = {
  id: "one", mode: "human", status: "open", channel: "whatsapp_cloud",
  reply_window_open: true, reply_window_until: "2026-09-08T00:00:00Z",
  created_at: "2026-09-01T00:00:00Z", updated_at: "2026-09-07T12:00:00Z", last_inbound_at: "2026-09-07T00:00:00Z",
} as Conversation;
const now = Date.parse("2026-09-07T15:00:00Z");
const incoming = { kind: "message", role: "user" } as Message;

test("server filters preserve unread and ownership rules across pagination", async () => {
  const requests = capture([]);
  await listConversations("https://inbox.example", session, {
    ...inboxFilters("open", "unread", " María & Pedro ", "team-a"), limit: 50, offset: 100,
  });
  const url = new URL(requests[0].url);
  assert.equal(url.pathname, "/api/portal/support/conversations");
  assert.deepEqual(Object.fromEntries(url.searchParams), {
    status: "open", team: "team-a", search: "María & Pedro", unread: "true", limit: "50", offset: "100",
  });
  assert.equal(new Headers(requests[0].init.headers).get("Authorization"), "Bearer phone-token");
  assert.equal(requests[0].init.credentials, "omit");
  assert.deepEqual(inboxFilters("open", "mine"), { status: "open", assignee: "me" });
  assert.deepEqual(inboxFilters("open", "unassigned"), { status: "open", assignee: "none" });
  assert.deepEqual(inboxFilters("resolved", "unread"), { status: "resolved" });
  assert.equal(conversationQuery({ limit: 900, offset: -1 }), "?limit=200&offset=0");
});

test("actions use portal methods and exact JSON payloads", async () => {
  const requests = capture();
  await reply("https://inbox.example", session, "one", "Hello", "quoted-id");
  await setStatus("https://inbox.example", session, "one", "resolved");
  await assignConversation("https://inbox.example", session, "one", "member-id");
  await setConversationTeam("https://inbox.example", session, "one", null);
  await reactToMessage("https://inbox.example", session, "one", "message-id", "");
  await replyWithTemplate("https://inbox.example", session, "one", { name: "welcome", language: "es", variables: ["Ana"] });
  assert.deepEqual(requests.map(({ url, init }) => [url.split("/one/")[1], init.method, JSON.parse(String(init.body))]), [
    ["reply", "POST", { content: "Hello", quoted_message_id: "quoted-id" }],
    ["status", "PATCH", { status: "resolved" }],
    ["assignment", "POST", { assignee_id: "member-id" }],
    ["team", "PATCH", { team_id: null }],
    ["messages/message-id/reaction", "POST", { emoji: "" }],
    ["reply-template", "POST", { name: "welcome", language: "es", variables: ["Ana"] }],
  ]);
});

test("read acknowledgement handles the 204 response", async () => {
  let called = false;
  global.fetch = async (url, init) => {
    called = true;
    assert.equal(url, "https://inbox.example/api/portal/support/conversations/one/read");
    assert.equal(init?.method, "POST");
    return new Response(null, { status: 204 });
  };
  assert.equal(await markRead("https://inbox.example", session, "one"), undefined);
  assert.equal(called, true);
});

test("summary comes from its own endpoint and contact notes are not public replies", async () => {
  const requests = capture();
  await getInboxSummary("https://inbox.example", session);
  await updateContact("https://inbox.example", session, "contact-id", { notes: "Follow up tomorrow", email: null });
  await listContactConversations("https://inbox.example", session, "contact-id");
  assert.equal(requests[0].url.endsWith("/conversations/summary"), true);
  assert.equal(requests[1].url.endsWith("/contacts/contact-id"), true);
  assert.deepEqual(JSON.parse(String(requests[1].init.body)), { notes: "Follow up tomorrow", email: null });
  assert.equal(requests[2].url.endsWith("/contacts/contact-id/conversations"), true);
});

test("API errors retain auth, conflict and validation status for screen recovery", async () => {
  for (const [status, body, message] of [
    [401, { detail: "Session expired" }, "Session expired"],
    [409, { detail: "Case is resolved" }, "Case is resolved"],
    [422, { detail: [{ msg: "Choose a valid phone" }] }, "Choose a valid phone"],
  ] as const) {
    global.fetch = async () => new Response(JSON.stringify(body), { status });
    await assert.rejects(listConversations("https://inbox.example", session), (error: unknown) =>
      error instanceof ApiError && error.status === status && error.message === message);
  }
  global.fetch = async () => { throw new TypeError("offline"); };
  await assert.rejects(listConversations("https://inbox.example", session), (error: unknown) => error instanceof ApiError && error.status === 0);
});

test("resolved cases stay locked regardless of mode or reply-window state", () => {
  assert.equal(canReply(open, now), true);
  assert.equal(canReply({ ...open, mode: "ai" }, now), false);
  for (const mode of ["human", "ai"] as const) {
    const resolved = { ...open, status: "resolved" as const, mode };
    assert.equal(canReply(resolved, now), false);
    assert.equal(canQuoteMessage(resolved, incoming, now), false);
    assert.equal(canReactToMessage(resolved, incoming), false);
  }
});

test("24-hour window expires between polls and server rejection takes precedence", () => {
  assert.equal(isReplyWindowClosed(open, now), false);
  assert.equal(canReply(open, Date.parse(open.reply_window_until!)), false);
  assert.equal(canReply({ ...open, reply_window_open: false }, now), false);
  assert.equal(canReply({ ...open, channel: "whatsapp", reply_window_open: false }, now), true);
  assert.equal(canReply({ ...open, channel: "widget", reply_window_until: null }, now), true);
});

test("quotes and reactions only target messages supported by the channel", () => {
  assert.equal(canQuoteMessage(open, incoming, now), true);
  assert.equal(canQuoteMessage({ ...open, channel: "widget" }, incoming, now), false);
  assert.equal(canQuoteMessage(open, { ...incoming, kind: "activity" }, now), false);
  assert.equal(canReactToMessage(open, incoming), true);
  assert.equal(canReactToMessage(open, { ...incoming, role: "assistant" }), false);
  assert.equal(canReactToMessage({ ...open, reply_window_open: false }, incoming), true);
});

test("overlapping pages refresh rows without duplicates and retain incoming order", () => {
  const two = { ...open, id: "two" };
  const updated = { ...two, unread_count: 2 };
  const three = { ...open, id: "three" };
  const rows = mergeConversationPages([open, two], [updated, three]);
  assert.deepEqual(rows.map((row) => row.id), ["one", "two", "three"]);
  assert.equal(rows[1].unread_count, 2);
  assert.equal(conversationTimestamp(open), open.last_inbound_at);
  assert.equal(conversationTimestamp({ ...open, last_inbound_at: null }), open.created_at);
});

test("saved replies use the same variable syntax as the portal", () => {
  assert.equal(interpolateCannedReply("Hi {contact_name}, I am {my_name} from {business_name}. {contact_phone}", {
    contact_name: "Ana", my_name: "Luis", business_name: "Studio", contact_phone: "",
  }), "Hi Ana, I am Luis from Studio. {contact_phone}");
});

test("WhatsApp group and private identifiers do not become fake phone numbers", () => {
  assert.equal(phoneFrom("573001234567@s.whatsapp.net"), "+573001234567");
  assert.equal(phoneFrom("573001234567:2@s.whatsapp.net"), "+573001234567");
  assert.equal(phoneFrom("12345678901234@g.us"), null);
  assert.equal(phoneFrom("12345678901234@lid"), null);
});

test("report requests preserve the local-day offset and backend filter names", async () => {
  const { getReport, createTeam, updateTeam } = await import("../src/api");
  const requests = capture();
  await getReport("https://inbox.example", session, { from: "2026-09-01", to: "2026-09-07", tz_offset: 300, team_id: "team-a", channel: "widget" });
  assert.deepEqual(Object.fromEntries(new URL(requests[0].url).searchParams), {
    from: "2026-09-01", to: "2026-09-07", tz_offset: "300", channel: "widget", team_id: "team-a",
  });
  const team = { name: "Support", description: "Help with orders", strategy: "least_busy" as const, channels: ["widget"], is_default: true, member_ids: ["member-a"] };
  await createTeam("https://inbox.example", session, team);
  await updateTeam("https://inbox.example", session, "team-a", team);
  assert.equal(requests[1].init.method, "POST");
  assert.equal(requests[2].init.method, "PATCH");
  assert.deepEqual(JSON.parse(String(requests[2].init.body)), team);
});

test("report ranges include today and durations distinguish missing data from zero", async () => {
  const { reportRange, formatDuration } = await import("../src/reports");
  const { workspaceStrings } = await import("../src/workspaceStrings");
  const today = new Date(2026, 8, 7, 20, 15);
  assert.deepEqual(reportRange(7, today), { from: "2026-09-01", to: "2026-09-07", tz_offset: today.getTimezoneOffset() });
  assert.equal(reportRange(30, today).from, "2026-08-09");
  const s = workspaceStrings();
  assert.equal(formatDuration(null, s), s.noData);
  assert.equal(formatDuration(0, s), `0 ${s.seconds}`);
  assert.equal(formatDuration(90, s), `2 ${s.minutes}`);
  assert.equal(formatDuration(3660, s), `1 ${s.hours} 1 ${s.minutes}`);
});
