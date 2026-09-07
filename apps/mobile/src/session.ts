/** Store bearer credentials in the operating system's encrypted credential store. */
import AsyncStorage from "@react-native-async-storage/async-storage";
import { Platform } from "react-native";
import * as SecureStore from "expo-secure-store";

const LEGACY_KEY = "inbox.session.v1";
const KEY = "inbox.session.v2";
const OPTIONS: SecureStore.SecureStoreOptions = {
  keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY,
};

export type StoredSession = { server: string; token: string };

// A browser preview has no native credential store. Keep its session in memory.
let previewSession: StoredSession | null = null;

function parse(raw: string | null): StoredSession | null {
  if (!raw) return null;
  try {
    const value: unknown = JSON.parse(raw);
    if (!value || typeof value !== "object") return null;
    const session = value as Partial<StoredSession>;
    if (typeof session.server !== "string" || typeof session.token !== "string" || !session.token) return null;
    const url = new URL(session.server);
    if (!["http:", "https:"].includes(url.protocol) || url.username || url.password) return null;
    return { server: session.server, token: session.token };
  } catch {
    return null;
  }
}

export async function loadStored(): Promise<StoredSession | null> {
  if (Platform.OS === "web") return previewSession;
  try {
    const stored = parse(await SecureStore.getItemAsync(KEY, OPTIONS));
    if (stored) {
      await AsyncStorage.removeItem(LEGACY_KEY).catch(() => {});
      return stored;
    }
    // Existing installs migrate once. Delete plaintext only after the encrypted
    // write succeeds, so a temporarily locked Keychain does not lose the login.
    const legacy = parse(await AsyncStorage.getItem(LEGACY_KEY));
    if (!legacy) return null;
    await SecureStore.setItemAsync(KEY, JSON.stringify(legacy), OPTIONS);
    await AsyncStorage.removeItem(LEGACY_KEY).catch(() => {});
    return legacy;
  } catch {
    return null;
  }
}

export async function store(session: StoredSession): Promise<void> {
  if (Platform.OS === "web") {
    previewSession = session;
    return;
  }
  // Never fall back to plaintext if the device cannot persist a credential.
  await SecureStore.setItemAsync(KEY, JSON.stringify(session), OPTIONS);
  await AsyncStorage.removeItem(LEGACY_KEY).catch(() => {});
}

export async function clearStored(): Promise<void> {
  previewSession = null;
  if (Platform.OS === "web") return;
  // If removing a legacy token fails, report sign-out failure. Otherwise a
  // later launch could migrate that token back and silently sign in again.
  await AsyncStorage.removeItem(LEGACY_KEY);
  await SecureStore.deleteItemAsync(KEY, OPTIONS);
}
