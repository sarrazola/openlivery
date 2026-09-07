import { useCallback, useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  AppState,
  BackHandler,
  Pressable,
  StatusBar,
  StyleSheet,
  Text,
  View,
} from "react-native";
import {
  SafeAreaProvider,
  SafeAreaView,
  useSafeAreaInsets,
} from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { WorkspaceScreen } from "./src/screens/WorkspaceScreen";
import { workspaceStrings } from "./src/workspaceStrings";
import { ContactsScreen } from "./src/screens/ContactsScreen";
import * as Notifications from "expo-notifications";
import * as SplashScreen from "expo-splash-screen";
import {
  ApiError,
  getConversation,
  resumeSession,
  type Conversation,
  type Session,
} from "./src/api";
import { startPushSession } from "./src/push";
import { clearStored, loadStored, store } from "./src/session";
import { clearComposerDrafts } from "./src/components/Composer";
import { ChatScreen } from "./src/screens/ChatScreen";
import { ConversationsScreen } from "./src/screens/ConversationsScreen";
import { SignInScreen } from "./src/screens/SignInScreen";
import { useStrings } from "./src/i18n";
import { readableBrand, useColors, useIsDark } from "./src/theme";
import { backDestination } from "./src/navigation";
import { notificationTarget } from "./src/notificationTarget";

type Screen =
  | { name: "loading" | "signIn" | "list" | "contacts" | "workspace" | "reconnect" }
  | { name: "chat"; conversation: Conversation };

function hideDevelopmentSplash() {
  // A development-client reload can replace the native splash observer.
  if (__DEV__) SplashScreen.hide();
}

export default function App() {
  return (
    <SafeAreaProvider>
      <InboxApp />
    </SafeAreaProvider>
  );
}

function InboxApp() {
  const [screen, setScreen] = useState<Screen>({ name: "loading" });
  const [server, setServer] = useState("");
  const [session, setSession] = useState<Session | null>(null);
  const [notification, setNotification] =
    useState<Notifications.NotificationResponse | null>(null);
  const stopPush = useRef<() => Promise<void>>(async () => {});
  const [signOutBusy, setSignOutBusy] = useState(false);
  const authGeneration = useRef(0);
  const handledNotification = useRef("");
  const signingOut = useRef(false);
  const returnTo = useRef<"list" | "contacts">("list");
  const insets = useSafeAreaInsets();
  const colors = useColors();
  const isDark = useIsDark();
  const s = useStrings();
  const w = workspaceStrings();
  function openConversation(conversation: Conversation) {
    if (screen.name === "list" || screen.name === "contacts")
      returnTo.current = screen.name;
    setScreen({ name: "chat", conversation });
  }

  const restore = useCallback(async () => {
    const generation = ++authGeneration.current;
    setScreen({ name: "loading" });
    const stored = await loadStored();
    if (generation !== authGeneration.current) return;
    if (!stored) {
      setScreen({ name: "signIn" });
      return;
    }
    try {
      const next = await resumeSession(stored.server, stored.token);
      if (generation !== authGeneration.current) return;
      setServer(stored.server);
      setSession(next);
      setScreen({ name: "list" });
    } catch (err) {
      if (generation !== authGeneration.current) return;
      if (err instanceof ApiError && err.status === 401) {
        await clearStored().catch(() => {});
        setScreen({ name: "signIn" });
      } else {
        // An offline launch must not erase a valid login.
        setScreen({ name: "reconnect" });
      }
    }
  }, []);
  useEffect(() => {
    void restore();
    return () => {
      authGeneration.current += 1;
    };
  }, [restore]);

  const handleSignOut = useCallback(async () => {
    if (signingOut.current) return;
    signingOut.current = true;
    setSignOutBusy(true);
    try {
      // A new account must not register the same native token before old
      // registration requests and their cleanup have finished.
      await stopPush.current();
      await clearStored();
      clearComposerDrafts();
      ++authGeneration.current;
      setSession(null);
      setServer("");
      setScreen({ name: "signIn" });
      setNotification(null);
      void Notifications.clearLastNotificationResponseAsync().catch(() => {});
    } catch (err) {
      // Restore notification registration if credential removal failed and
      // the user remains signed in.
      if (session) setSession({ ...session });
      Alert.alert(
        s.errors.generic,
        err instanceof Error ? err.message : s.errors.generic,
      );
    } finally {
      signingOut.current = false;
      setSignOutBusy(false);
    }
  }, [server, session, s]);

  const expireSession = useCallback(() => {
    void handleSignOut();
  }, [handleSignOut]);
  async function handleSignedIn(base: string, next: Session) {
    await store({ server: base, token: next.token });
    ++authGeneration.current;
    setServer(base);
    setSession(next);
    setScreen({ name: "list" });
  }

  useEffect(() => {
    if (!session) return;
    const stop = startPushSession(server, session);
    stopPush.current = stop;
    return () => {
      void stop();
    };
  }, [server, session]);

  useEffect(() => {
    let active = true;
    let receivedLiveResponse = false;
    void Notifications.getLastNotificationResponseAsync()
      .then((response) => {
        if (active && !receivedLiveResponse) setNotification(response);
      })
      .catch(() => {});
    const subscription =
      Notifications.addNotificationResponseReceivedListener((response) => {
        receivedLiveResponse = true;
        setNotification(response);
      });
    return () => {
      active = false;
      subscription.remove();
    };
  }, []);
  useEffect(() => {
    if (!notification || !session || signOutBusy) return;
    const identifier = notification.notification.request.identifier;
    if (handledNotification.current === identifier) return;
    handledNotification.current = identifier;
    const id = notificationTarget(notification.notification.request.content.data, session.client_id);
    if (!id) {
      void Notifications.clearLastNotificationResponseAsync().catch(() => {});
      return;
    }
    let active = true;
    void getConversation(server, session, id)
      .then((conversation) => {
        if (active) {
          returnTo.current = "list";
          setScreen({ name: "chat", conversation });
        }
      })
      .catch((err) => {
        if (!active) return;
        if (err instanceof ApiError && err.status === 401) expireSession();
        else
          Alert.alert(
            s.inbox.notificationUnavailable,
            err instanceof Error ? err.message : undefined,
          );
      })
      .finally(() => {
        void Notifications.clearLastNotificationResponseAsync().catch(() => {});
      });
    return () => {
      active = false;
    };
  }, [notification, server, session, expireSession, s, signOutBusy]);

  useEffect(() => {
    if (!session) return;
    let active = true;
    const subscription = AppState.addEventListener("change", (state) => {
      if (state !== "active") return;
      void resumeSession(server, session.token).catch((err) => {
        if (active && err instanceof ApiError && err.status === 401)
          expireSession();
      });
    });
    return () => {
      active = false;
      subscription.remove();
    };
  }, [server, session, expireSession]);
  useEffect(() => {
    const subscription = BackHandler.addEventListener(
      "hardwareBackPress",
      () => {
        const destination = backDestination(screen.name, returnTo.current);
        if (!destination) return false;
        setScreen({ name: destination });
        return true;
      },
    );
    return () => subscription.remove();
  }, [screen.name]);

  return (
    <View onLayout={hideDevelopmentSplash} style={[styles.root, { backgroundColor: colors.canvas }]}>
      <StatusBar
        barStyle={isDark ? "light-content" : "dark-content"}
        backgroundColor={colors.surface}
      />
      {screen.name === "loading" ? (
        <SafeAreaView style={styles.center}>
          <ActivityIndicator color={colors.muted} />
        </SafeAreaView>
      ) : screen.name === "reconnect" ? (
        <SafeAreaView style={styles.center}>
          <Text style={[styles.title, { color: colors.ink }]}>
            {s.inbox.reconnectTitle}
          </Text>
          <Text style={[styles.body, { color: colors.muted }]}>
            {s.inbox.reconnectBody}
          </Text>
          <Pressable onPress={() => void restore()} style={styles.retry}>
            <Text style={{ color: colors.ink, fontWeight: "700" }}>
              {s.inbox.retry}
            </Text>
          </Pressable>
          <Pressable onPress={() => void handleSignOut()} style={styles.retry}>
            <Text style={{ color: colors.muted }}>{s.inbox.signOut}</Text>
          </Pressable>
        </SafeAreaView>
      ) : screen.name === "signIn" || !session ? (
        <SafeAreaView style={styles.root}>
          <SignInScreen onSignedIn={handleSignedIn} />
        </SafeAreaView>
      ) : (
        <View style={styles.root}>
          <View
            style={[styles.root, screen.name !== "list" && { display: "none" }]}
          >
            <ConversationsScreen
              server={server}
              session={session}
              active={screen.name === "list"}
              onOpen={openConversation}
              onSignOut={() => void handleSignOut()}
              onSessionExpired={expireSession}
            />
          </View>
          {screen.name === "contacts" && (
            <ContactsScreen
              server={server}
              session={session}
              onBack={() => setScreen({ name: "list" })}
              onOpenConversation={openConversation}
              onSessionExpired={expireSession}
            />
          )}
          {screen.name === "workspace" && <WorkspaceScreen server={server} session={session} onBack={() => setScreen({ name: "list" })} onSessionExpired={expireSession} />}
          {screen.name !== "chat" && (
            <View
              style={{
                flexDirection: "row",
                backgroundColor: colors.surface,
                borderTopWidth: StyleSheet.hairlineWidth,
                borderTopColor: colors.line,
                paddingBottom: insets.bottom,
              }}
            >
              {(["list", "contacts", "workspace"] as const).map((name) => (
                <Pressable
                  key={name}
                  onPress={() => setScreen({ name })}
                  style={{
                    flex: 1,
                    alignItems: "center",
                    justifyContent: "center",
                    gap: 3,
                    minHeight: 56,
                  }}
                  accessibilityRole="tab"
                  accessibilityState={{ selected: screen.name === name }}
                  testID={`navigation-${name}`}
                >
                  <Ionicons
                    name={
                      name === "list" ? "chatbubbles-outline" : name === "contacts" ? "people-outline" : "grid-outline"
                    }
                    size={22}
                    color={
                      screen.name === name
                        ? readableBrand(session.branding.brand_color, isDark)
                        : colors.muted
                    }
                  />
                  <Text
                    style={{
                      fontSize: 11,
                      fontWeight: "600",
                      color: screen.name === name ? colors.ink : colors.muted,
                    }}
                  >
                    {name === "list" ? s.inbox.title : name === "contacts" ? s.inbox.contacts : w.title}
                  </Text>
                </Pressable>
              ))}
            </View>
          )}
          {screen.name === "chat" && (
            <ChatScreen
              key={screen.conversation.id}
              server={server}
              session={session}
              conversation={screen.conversation}
              onBack={() => setScreen({ name: returnTo.current })}
              onSessionExpired={expireSession}
              onOpenConversation={openConversation}
            />
          )}
        </View>
      )}
      {signOutBusy && (
        <View style={[StyleSheet.absoluteFill, styles.center, { backgroundColor: colors.canvas, zIndex: 100 }]} accessibilityLabel={s.inbox.signOut}>
          <ActivityIndicator color={colors.muted} />
        </View>
      )}
    </View>
  );
}
const styles = StyleSheet.create({
  root: { flex: 1 },
  center: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    padding: 30,
  },
  title: { fontSize: 22, fontWeight: "700" },
  body: { fontSize: 16, lineHeight: 23, textAlign: "center", marginTop: 12 },
  retry: {
    minHeight: 48,
    paddingHorizontal: 24,
    alignItems: "center",
    justifyContent: "center",
    marginTop: 12,
  },
});
