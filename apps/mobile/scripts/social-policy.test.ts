import assert from "node:assert/strict";
import { test } from "node:test";
import type { Conversation, Message } from "../src/api";
import { conversationQuery } from "../src/api";
import { channelIcon, channelLabel, conversationName } from "../src/conversations";
import { strings } from "../src/i18n";
import {
  acceptsAttachment, canQuoteMessage, canReactToMessage, canReply, channelCapabilities,
  deliveryPresentation, humanWindowOnly, inboxFilters, isReplyWindowClosed,
} from "../src/inbox";

const now = Date.parse("2026-09-07T12:00:00Z");
const within24Hours = {
  channel: "instagram", status: "open", mode: "human", reply_window_open: true,
  reply_window_until: "2026-09-08T11:00:00Z", human_reply_window_open: true,
  human_reply_window_until: "2026-09-08T11:00:00Z", reply_block_reason: null,
  channel_capabilities: { text: true, image: true, audio: true, video: true, file: true, quotes: false, reactions: false, templates: false },
} as Conversation;

for (const channel of ["instagram", "messenger"]) {
  test(`${channel} closes replies locally at expiry and rejects unknown policy`, () => {
    const thread = { ...within24Hours, channel };
    assert.equal(canReply(thread, now), true);
    assert.equal(canReply(thread, Date.parse(thread.reply_window_until!)), false);
    assert.equal(canReply({ ...thread, reply_window_open: false, human_reply_window_open: false }, now), false);
    assert.equal(canReply({ ...thread, reply_window_until: "invalid", human_reply_window_until: null }, now), false);
    assert.equal(canReply({ channel, status: "open", mode: "human" } as Conversation, now), false);
  });

  test(`${channel} human extension permits manual replies but never AI, quotes or reactions`, () => {
    const thread = { ...within24Hours, channel, reply_window_open: false,
      reply_window_until: "2026-09-06T12:00:00Z", human_reply_window_until: "2026-09-12T12:00:00Z" };
    assert.equal(humanWindowOnly(thread, now), true);
    assert.equal(canReply(thread, now), true);
    assert.equal(canReply({ ...thread, mode: "ai" }, now), false);
    assert.equal(canReply({ ...thread, status: "resolved" }, now), false);
    assert.equal(canReply(thread, Date.parse(thread.human_reply_window_until)), false);
    const message = { kind: "message", role: "user" } as Message;
    assert.equal(canQuoteMessage(thread, message, now), false);
    assert.equal(canReactToMessage(thread, message), false);
  });
}

test("server disconnect, revocation and control decisions override future windows", () => {
  for (const reply_block_reason of ["channel_disconnected", "authorization_expired", "another_app_controls_conversation", "conversation_resolved", "reply_window_closed"]) {
    const thread = { ...within24Hours, reply_block_reason };
    assert.equal(isReplyWindowClosed(thread, now), true);
    assert.equal(canReply(thread, now), false);
    assert.equal(humanWindowOnly(thread, now), false);
  }
});

test("social attachments require advertised capabilities and Instagram documents are PDF only", () => {
  const capabilities = channelCapabilities(within24Hours);
  for (const mime of ["image/png", "audio/mp4", "video/mp4", "application/pdf"]) assert.equal(acceptsAttachment("instagram", capabilities, mime), true);
  assert.equal(acceptsAttachment("instagram", capabilities, "application/msword"), false);
  assert.equal(acceptsAttachment("messenger", capabilities, "application/msword"), true);
  assert.equal(acceptsAttachment("instagram", { ...capabilities, audio: false }, "audio/mp4"), false);
  assert.equal(acceptsAttachment("instagram", channelCapabilities({ channel: "instagram" }), "image/png"), false);
  assert.equal(acceptsAttachment("widget", channelCapabilities({ channel: "widget" }), "application/pdf"), true);
});

test("pending and ambiguous delivery never receive delivered ticks", () => {
  assert.deepEqual(deliveryPresentation("pending"), { label: "pending", icon: "time-outline" });
  assert.deepEqual(deliveryPresentation("unknown"), { label: "unknown", icon: "help-circle-outline" });
  assert.equal(deliveryPresentation("failed")?.label, "failed");
  assert.equal(deliveryPresentation("unexpected-provider-state")?.label, "unknown");
  assert.equal(deliveryPresentation("delivered")?.icon, "checkmark-done");
  assert.equal(deliveryPresentation(null), null);
});

test("social labels, icons and filters identify the actual channel without inventing a phone", () => {
  const s = strings();
  assert.equal(channelLabel("instagram", s), "Instagram");
  assert.equal(channelLabel("messenger", s), "Facebook Messenger");
  assert.equal(channelIcon("instagram"), "logo-instagram");
  assert.equal(channelIcon("messenger"), "logo-facebook");
  assert.equal(conversationName({ channel: "instagram", external_chat_id: "123456789012345", contact_name: null, title: "Instagram contact" }, s), "Instagram contact");
  const params = new URLSearchParams(conversationQuery(inboxFilters("open", "unread", "Ana", "support", "messenger")));
  assert.equal(params.get("channel"), "messenger");
  assert.equal(params.get("team"), "support");
  assert.equal(params.get("unread"), "true");
});
