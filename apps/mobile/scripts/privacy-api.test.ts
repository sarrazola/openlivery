import assert from "node:assert/strict";
import { test } from "node:test";
import { forgetDevice, getConversation, listConversations, registerDevice, replyWithFile, resumeSession, setSessionAccess, type Session } from "../src/api";

test("pending permission blocks portal reads, uploads and push registration while allowing validation and cleanup", async () => {
  const session = { token: "privacy-test-token", portal_slug: "example" } as Session;
  const original = global.fetch;
  const called: string[] = [];
  global.fetch = async (url, init) => {
    called.push(String(url));
    return init?.method === "DELETE" ? new Response(null, { status: 204 }) : Response.json({});
  };
  try {
    setSessionAccess(session, false);
    assert.throws(() => listConversations("https://example.test", session), { status: 428 });
    assert.throws(() => getConversation("https://example.test", session, "case"), { status: 428 });
    await assert.rejects(registerDevice("https://example.test", session, { token: "native-token", provider: "webhook", platform: "ios" }), { status: 428 });
    await assert.rejects(replyWithFile("https://example.test", session, "case", { uri: "file:///voice.m4a", name: "voice.m4a", type: "audio/mp4" }), { status: 428 });
    assert.deepEqual(called, []);
    await resumeSession("https://example.test", session.token);
    await forgetDevice("https://example.test", session, "native-token");
    assert.equal(called.length, 2);
    setSessionAccess(session, true);
    await listConversations("https://example.test", session);
    assert.equal(called.length, 3);
  } finally {
    global.fetch = original;
    setSessionAccess(session, true);
  }
});
