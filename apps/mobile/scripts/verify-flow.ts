/**
 * End-to-end check of the app's data layer against a running server.
 *
 * It imports the same module the screens use, so what passes here is what the
 * phone does: sign in, list conversations, open one, take over, reply, hand
 * back. Meant to be run against a local instance while developing.
 *
 *   SERVER=http://localhost:8000 EMAIL=... PASSWORD=... npx tsx scripts/verify-flow.ts
 */

import {
  attachmentUrl,
  authHeaders,
  forgetDevice,
  getConversation,
  listConversations,
  normalizeServerUrl,
  registerDevice,
  reply,
  resumeSession,
  setMode,
  signIn,
} from "../src/api";

const SERVER = normalizeServerUrl(process.env.SERVER || "http://localhost:8000");
const EMAIL = process.env.EMAIL || "";
const PASSWORD = process.env.PASSWORD || "";

let failures = 0;

function check(label: string, ok: boolean, detail = "") {
  const mark = ok ? "PASS" : "FAIL";
  if (!ok) failures += 1;
  console.log(`  [${mark}] ${label}${detail ? ` — ${detail}` : ""}`);
}

async function main() {
  if (!EMAIL || !PASSWORD) {
    console.error("Set EMAIL and PASSWORD to the portal credentials of a client.");
    process.exit(2);
  }

  console.log(`\nServer: ${SERVER}\n`);

  console.log("Sign in");
  const session = await signIn(SERVER, EMAIL, PASSWORD);
  check("returns a token", Boolean(session.token));
  check("resolves the portal without being told the slug", Boolean(session.portal_slug), session.portal_slug);
  check("carries branding for the agency", Boolean(session.branding.agency_name), session.branding.agency_name);
  check("carries a brand colour", /^#[0-9a-f]{6}$/i.test(session.branding.brand_color), session.branding.brand_color);

  console.log("\nWrong password");
  try {
    await signIn(SERVER, EMAIL, `${PASSWORD}-wrong`);
    check("is rejected", false, "it was accepted");
  } catch (err: any) {
    check("is rejected with 401", err?.status === 401, `status ${err?.status}`);
  }

  console.log("\nResume a stored token");
  const resumed = await resumeSession(SERVER, session.token);
  check("returns the same portal", resumed.portal_slug === session.portal_slug);
  try {
    await resumeSession(SERVER, "not-a-token");
    check("rejects a bad token", false, "it was accepted");
  } catch (err: any) {
    check("rejects a bad token", err?.status === 401, `status ${err?.status}`);
  }

  console.log("\nConversations");
  const conversations = await listConversations(SERVER, session);
  check("lists conversations", Array.isArray(conversations), `${conversations.length} found`);
  if (!conversations.length) {
    console.log("\nNo conversations to open; send one message to the agent first.");
    process.exit(failures ? 1 : 0);
  }

  const target = conversations[0];
  const detail = await getConversation(SERVER, session, target.id);
  check("opens one and returns its messages", Array.isArray(detail.messages), `${detail.messages.length} messages`);

  console.log("\nHuman takeover");
  const taken = await setMode(SERVER, session, target.id, "human");
  check("switches to human", taken.mode === "human", taken.mode);

  const text = `Automated check ${new Date().toISOString()}`;
  const afterReply = await reply(SERVER, session, target.id, text);
  const landed = afterReply.messages.some((m) => m.content === text);
  check("the reply is stored in the conversation", landed);

  console.log("\nAttachments");
  // A one-pixel PNG is enough: what is being checked is the round trip, not the
  // picture. Node has no expo-file-system, so the multipart body is built the
  // way a browser would - the app's own path is exercised on a device.
  const png = Buffer.from(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==",
    "base64",
  );
  const form = new FormData();
  form.append("file", new Blob([png], { type: "image/png" }), "verify.png");
  form.append("caption", "Automated attachment check");
  const uploaded = await fetch(
    `${SERVER}/api/portal/${session.portal_slug}/conversations/${target.id}/reply-media`,
    { method: "POST", body: form, headers: authHeaders(session) },
  );
  check("sends a file into the conversation", uploaded.ok, `status ${uploaded.status}`);
  if (uploaded.ok) {
    const withMedia = await uploaded.json();
    const last = withMedia.messages[withMedia.messages.length - 1];
    const attachment = last?.attachments?.[0];
    check("the message carries the attachment", Boolean(attachment), attachment?.mime);
    check("it is recognised as an image", attachment?.kind === "image", attachment?.kind);
    if (attachment) {
      const fetched = await fetch(
        attachmentUrl(SERVER, session, target.id, attachment.id),
        { headers: authHeaders(session) },
      );
      check("it can be fetched back with the session", fetched.ok, `status ${fetched.status}`);
      const naked = await fetch(attachmentUrl(SERVER, session, target.id, attachment.id));
      check("and not without it", naked.status === 401, `status ${naked.status}`);
    }
  }

  console.log("\nNotifications");
  // The device registry accepts a registration whether or not the server has a
  // provider; what it reports back is what the app uses to decide.
  const deviceToken = `verify-${Date.now().toString(16)}${"0".repeat(8)}`;
  const registered = await registerDevice(SERVER, session, {
    token: deviceToken,
    provider: session.push.provider,
    platform: "ios",
  });
  check("registers a device", typeof registered.registered === "boolean");
  check(
    "the session and the registry agree on the provider",
    registered.provider === session.push.provider,
    `${session.push.provider} vs ${registered.provider}`,
  );
  await forgetDevice(SERVER, session, deviceToken);
  check("releases it again", true);

  const handedBack = await setMode(SERVER, session, target.id, "ai");
  check("hands back to the assistant", handedBack.mode === "ai", handedBack.mode);

  console.log(`\n${failures ? `${failures} check(s) failed` : "All checks passed"}\n`);
  process.exit(failures ? 1 : 0);
}

main().catch((err) => {
  console.error("\nUnexpected failure:", err?.message || err);
  process.exit(1);
});
