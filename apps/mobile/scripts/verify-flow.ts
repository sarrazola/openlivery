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
  getConversation,
  listConversations,
  normalizeServerUrl,
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

  const handedBack = await setMode(SERVER, session, target.id, "ai");
  check("hands back to the assistant", handedBack.mode === "ai", handedBack.mode);

  console.log(`\n${failures ? `${failures} check(s) failed` : "All checks passed"}\n`);
  process.exit(failures ? 1 : 0);
}

main().catch((err) => {
  console.error("\nUnexpected failure:", err?.message || err);
  process.exit(1);
});
