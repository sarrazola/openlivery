/** Permission is specific to the account, workspace and disclosed processing. */
import { Platform } from "react-native";
import * as SecureStore from "expo-secure-store";
import type { Session } from "./api";

const KEY = "inbox.privacy.v1";
const OPTIONS = { keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY };
let previewConsent: string | null = null;

export function consentFingerprint(server: string, session: Session): string | null {
  const privacy = session.privacy;
  if (!privacy || typeof privacy.version !== "string" || !privacy.version || !Array.isArray(privacy.destinations)) return null;
  if (privacy.destinations.some((row) => !row || !["ai", "integration", "notification"].includes(row.kind)
    || typeof row.name !== "string" || typeof row.host !== "string" || !Array.isArray(row.capabilities)
    || row.capabilities.some((value) => typeof value !== "string"))) return null;
  try {
    const url = new URL(server);
    if (!["https:", "http:"].includes(url.protocol) || url.username || url.password) return null;
    return JSON.stringify({
      policy: "1", server: url.origin + url.pathname.replace(/\/+$/, ""),
      client: session.client_id, user: session.user_id || "legacy", version: privacy.version,
      destinations: privacy.destinations.map((row) => ({ ...row, capabilities: [...row.capabilities].sort() }))
        .sort((a, b) => JSON.stringify(a).localeCompare(JSON.stringify(b))),
    });
  } catch { return null; }
}

export async function hasConsent(server: string, session: Session): Promise<boolean> {
  const expected = consentFingerprint(server, session);
  if (!expected) return false;
  try {
    const saved = Platform.OS === "web" ? previewConsent : await SecureStore.getItemAsync(KEY, OPTIONS);
    return saved === expected;
  } catch { return false; }
}

export async function acceptConsent(server: string, session: Session): Promise<void> {
  const value = consentFingerprint(server, session);
  if (!value) throw new Error("The server must provide its processing disclosure.");
  if (Platform.OS === "web") previewConsent = value;
  else await SecureStore.setItemAsync(KEY, value, OPTIONS);
}

export async function withdrawConsent(): Promise<void> {
  previewConsent = null;
  if (Platform.OS !== "web") await SecureStore.deleteItemAsync(KEY, OPTIONS);
}
