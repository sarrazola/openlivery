/**
 * Registering this install for notifications, without choosing a provider.
 *
 * The app asks the operating system for the native push token - APNs on iOS,
 * FCM on Android - and hands it to the server, which delivers through whatever
 * it was configured with. No push vendor's SDK is involved, which is what lets
 * the same build work against a server that sends nothing, a server that POSTs
 * to the operator's own webhook, and a hosted one, without any of them
 * borrowing another's account.
 *
 * Two rules this module exists to keep:
 *
 * 1. If the server says it cannot notify, ask for nothing. A permission prompt
 *    that leads to no notifications trains people to say no, and a device that
 *    subscribes to a push service nobody asked for costs whoever owns that
 *    service money.
 * 2. Never let any of this break the app. Notifications are a convenience on
 *    top of an inbox that already works by polling, so every failure here is
 *    swallowed and reported through the returned state instead.
 */

import { Platform } from "react-native";
import * as Device from "expo-device";
import * as Notifications from "expo-notifications";
import { forgetDevice, registerDevice, type Session } from "./api";
import { strings } from "./i18n";

export type PushState =
  | { status: "off" }             // the server does not send notifications
  | { status: "denied" }          // the person declined, or the OS refused
  | { status: "unavailable" }     // a simulator, or no push support
  | { status: "registered"; token: string };

/** Show a banner even while the app is open; the inbox is not always on screen. */
Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowBanner: true,
    shouldShowList: true,
    shouldPlaySound: true,
    shouldSetBadge: false,
  }),
});

async function nativeToken(): Promise<string | null> {
  const existing = await Notifications.getPermissionsAsync();
  const allowed = (permission: Notifications.NotificationPermissionsStatus) => permission.granted
    || permission.ios?.status === Notifications.IosAuthorizationStatus.PROVISIONAL
    || permission.ios?.status === Notifications.IosAuthorizationStatus.EPHEMERAL;
  let granted = allowed(existing);
  if (!granted && existing.canAskAgain) {
    granted = allowed(await Notifications.requestPermissionsAsync());
  }
  if (!granted) return null;
  const token = await Notifications.getDevicePushTokenAsync();
  return typeof token.data === "string" && token.data ? token.data : null;
}

/** Permission dialogs are OS-owned; cancelling a session must not wait for one. */
function cancellableNativeToken(signal?: AbortSignal): Promise<string | null> {
  if (!signal) return nativeToken();
  if (signal.aborted) return Promise.resolve(null);
  return new Promise((resolve, reject) => {
    const cancel = () => resolve(null);
    signal.addEventListener("abort", cancel, { once: true });
    void nativeToken().then(resolve, reject).finally(() => signal.removeEventListener("abort", cancel));
  });
}

/**
 * Register for notifications if - and only if - the server can send them.
 *
 * Returns what happened so the caller can say so honestly rather than leaving
 * someone to wonder why their phone is silent.
 */
export async function enablePush(server: string, session: Session, signal?: AbortSignal): Promise<PushState> {
  if (!session.push?.enabled) return { status: "off" };
  // A simulator has no push token to give, and asking would only produce a
  // permission prompt that can never lead to anything.
  if (Platform.OS === "web" || !Device.isDevice) return { status: "unavailable" };
  try {
    if (Platform.OS === "android") {
      // Android 13 cannot present the permission prompt until a channel exists.
      await Notifications.setNotificationChannelAsync("messages", {
        name: strings().notifications.channelName,
        importance: Notifications.AndroidImportance.HIGH,
        sound: "default",
      });
    }
    const token = await cancellableNativeToken(signal);
    if (signal?.aborted) return { status: "off" };
    if (!token) return { status: "denied" };
    await registerDevice(server, session, {
      token,
      provider: session.push.provider,
      platform: Platform.OS,
    });
    return { status: "registered", token };
  } catch {
    // A simulator has no push support, and a person can revoke permission at
    // any time. Neither is worth an error on screen.
    return { status: "unavailable" };
  }
}

/** Keep the registry current if APNs/FCM rotates the token while the app is open. */
export function watchPushToken(
  server: string,
  session: Session,
  onRegistered: (token: string) => void,
): () => Promise<void> {
  if (!session.push?.enabled || Platform.OS === "web" || !Device.isDevice) return async () => {};
  let active = true;
  const pending = new Set<Promise<void>>();
  const registered = new Set<string>();
  const subscription = Notifications.addPushTokenListener((next) => {
    if (!active || typeof next.data !== "string" || !next.data) return;
    const token = next.data;
    const operation = registerDevice(server, session, {
      token,
      provider: session.push.provider,
      platform: Platform.OS,
    }).then(() => {
      registered.add(token);
      if (active) onRegistered(token);
    }).catch(() => {});
    pending.add(operation);
    void operation.finally(() => pending.delete(operation));
  });
  let stopping: Promise<void> | null = null;
  return () => {
    if (stopping) return stopping;
    active = false;
    subscription.remove();
    stopping ??= Promise.all([...pending]).then(async () => {
      await Promise.all([...registered].map((token) => disablePush(server, session, token)));
    });
    return stopping;
  };
}

/** Dispose fully before another account registers this install's native token. */
export function startPushSession(server: string, session: Session): () => Promise<void> {
  const controller = new AbortController();
  let firstToken: string | null = null;
  const registration = enablePush(server, session, controller.signal).then((state) => {
    if (state.status === "registered") firstToken = state.token;
  });
  const stopWatching = watchPushToken(server, session, () => {});
  let stopping: Promise<void> | null = null;
  return () => {
    controller.abort();
    stopping ??= Promise.all([registration, stopWatching()]).then(async () => {
      await disablePush(server, session, firstToken);
    });
    return stopping;
  };
}

/** Release this install on sign-out so a shared phone stops ringing. */
export async function disablePush(server: string, session: Session, token: string | null): Promise<void> {
  if (!token) return;
  try {
    await forgetDevice(server, session, token);
  } catch {
    // Signing out locally matters more than tidying the server's registry,
    // which drops the row anyway once the token stops accepting deliveries.
  }
}
