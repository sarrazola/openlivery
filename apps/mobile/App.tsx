import { useEffect, useRef, useState } from "react";
import { ActivityIndicator, StatusBar, StyleSheet, View } from "react-native";
import { SafeAreaProvider, SafeAreaView } from "react-native-safe-area-context";
import { resumeSession, type Conversation, type Session } from "./src/api";
import { disablePush, enablePush } from "./src/push";
import { clearStored, loadStored, store } from "./src/session";
import { ChatScreen } from "./src/screens/ChatScreen";
import { ConversationsScreen } from "./src/screens/ConversationsScreen";
import { SignInScreen } from "./src/screens/SignInScreen";
import { useColors, useIsDark } from "./src/theme";

type Screen = { name: "loading" } | { name: "signIn" } | { name: "list" } | { name: "chat"; conversation: Conversation };


/**
 * Three screens and no navigation library: sign in, the list, one conversation.
 * The stack never goes deeper than this, so a router would be more moving parts
 * than the app has states.
 */
export default function App() {
  const [screen, setScreen] = useState<Screen>({ name: "loading" });
  const [server, setServer] = useState("");
  const [session, setSession] = useState<Session | null>(null);
  // The push token this install registered, so sign-out can release it.
  const deviceToken = useRef<string | null>(null);

  // Resume a stored session on launch, which also refreshes branding.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const stored = await loadStored();
      if (!stored) {
        if (!cancelled) setScreen({ name: "signIn" });
        return;
      }
      try {
        const resumed = await resumeSession(stored.server, stored.token);
        if (cancelled) return;
        setServer(stored.server);
        setSession(resumed);
        setScreen({ name: "list" });
        registerForPush(stored.server, resumed);
      } catch {
        // Expired, revoked, or the server is unreachable: ask again rather than
        // leaving the person staring at a spinner.
        await clearStored();
        if (!cancelled) setScreen({ name: "signIn" });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  /**
   * Ask for notifications only once there is a session, and only if the server
   * says it can send them. Deliberately not awaited: the inbox already works by
   * polling, so nothing here should hold up showing it.
   */
  function registerForPush(base: string, next: Session) {
    enablePush(base, next).then((state) => {
      deviceToken.current = state.status === "registered" ? state.token : null;
    });
  }

  async function handleSignedIn(base: string, next: Session) {
    setServer(base);
    setSession(next);
    await store({ server: base, token: next.token });
    setScreen({ name: "list" });
    registerForPush(base, next);
  }

  async function handleSignOut() {
    // Release the device before the token goes, or this phone keeps ringing for
    // whoever was signed in - which on a shared phone is the wrong person.
    if (session) await disablePush(server, session, deviceToken.current);
    deviceToken.current = null;
    await clearStored();
    setSession(null);
    setServer("");
    setScreen({ name: "signIn" });
  }

  return (
    <SafeAreaProvider>
      <Shell
        screen={screen}
        server={server}
        session={session}
        onSignedIn={handleSignedIn}
        onSignOut={handleSignOut}
        onOpen={(conversation) => setScreen({ name: "chat", conversation })}
        onBack={() => setScreen({ name: "list" })}
      />
    </SafeAreaProvider>
  );
}

/**
 * Split out from App so the colour hooks run inside SafeAreaProvider, and so
 * the whole tree re-renders when the phone switches between light and dark.
 */
function Shell({
  screen,
  server,
  session,
  onSignedIn,
  onSignOut,
  onOpen,
  onBack,
}: {
  screen: Screen;
  server: string;
  session: Session | null;
  onSignedIn: (server: string, session: Session) => void;
  onSignOut: () => void;
  onOpen: (conversation: Conversation) => void;
  onBack: () => void;
}) {
  const colors = useColors();
  const isDark = useIsDark();

  return (
    <View style={[styles.root, { backgroundColor: colors.canvas }]}>
      {/* The bars are system-coloured now, so the status bar follows the scheme
          rather than being forced light over a painted header. */}
      <StatusBar barStyle={isDark ? "light-content" : "dark-content"} backgroundColor={colors.surface} />
      {screen.name === "loading" ? (
        <SafeAreaView style={styles.center}>
          <ActivityIndicator color={colors.muted} />
        </SafeAreaView>
      ) : screen.name === "signIn" || !session ? (
        <SafeAreaView style={styles.flex}>
          <SignInScreen onSignedIn={onSignedIn} />
        </SafeAreaView>
      ) : screen.name === "chat" ? (
        <ChatScreen
          server={server}
          session={session}
          conversation={screen.conversation}
          onBack={onBack}
        />
      ) : (
        <ConversationsScreen
          server={server}
          session={session}
          onOpen={onOpen}
          onSignOut={onSignOut}
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1 },
  flex: { flex: 1 },
  center: { flex: 1, alignItems: "center", justifyContent: "center" },
});
