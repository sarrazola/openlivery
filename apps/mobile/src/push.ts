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
  let granted = existing.granted;
  if (!granted && existing.canAskAgain) {
    granted = (await Notifications.requestPermissionsAsync()).granted;
  }
  if (!granted) return null;
  const token = await Notifications.getDevicePushTokenAsync();
  return typeof token.data === "string" ? token.data : null;
}

/**
 * Register for notifications if - and only if - the server can send them.
 *
 * Returns what happened so the caller can say so honestly rather than leaving
 * someone to wonder why their phone is silent.
 */
export async function enablePush(server: string, session: Session): Promise<PushState> {
  if (!session.push?.enabled) return { status: "off" };
  // A simulator has no push token to give, and asking would only produce a
  // permission prompt that can never lead to anything.
  if (!Device.isDevice) return { status: "unavailable" };
  try {
    const token = await nativeToken();
    if (!token) return { status: "denied" };
    await registerDevice(server, session, {
      token,
      provider: session.push.provider,
      platform: Platform.OS,
    });
    if (Platform.OS === "android") {
      // Android needs a channel before anything it delivers makes a sound.
      await Notifications.setNotificationChannelAsync("messages", {
        name: "Messages",
        importance: Notifications.AndroidImportance.HIGH,
        sound: "default",
      });
    }
    return { status: "registered", token };
  } catch {
    // A simulator has no push support, and a person can revoke permission at
    // any time. Neither is worth an error on screen.
    return { status: "unavailable" };
  }
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
