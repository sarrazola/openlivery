/**
 * Keeps the signed-in session on the device.
 *
 * Only the server address and the token are persisted; branding is re-fetched
 * on launch so a colour or logo the agency changes shows up without signing in
 * again. AsyncStorage is not a secure store - the token is a portal session
 * scoped to one client, which is the same exposure as leaving the browser
 * portal open, and a stolen device is out of scope for this app.
 */

import AsyncStorage from "@react-native-async-storage/async-storage";

const KEY = "openlivery.session.v1";

export type StoredSession = { server: string; token: string };

export async function loadStored(): Promise<StoredSession | null> {
  try {
    const raw = await AsyncStorage.getItem(KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (typeof parsed?.server === "string" && typeof parsed?.token === "string") return parsed;
    return null;
  } catch {
    return null;
  }
}

export async function store(session: StoredSession): Promise<void> {
  try {
    await AsyncStorage.setItem(KEY, JSON.stringify(session));
  } catch {
    // A device that cannot persist still works for the current session.
  }
}

export async function clearStored(): Promise<void> {
  try {
    await AsyncStorage.removeItem(KEY);
  } catch {}
}
