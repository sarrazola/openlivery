import { useEffect, useState } from "react";
import { ActivityIndicator, StatusBar, StyleSheet, View } from "react-native";
import { SafeAreaProvider, SafeAreaView } from "react-native-safe-area-context";
import { resumeSession, type Conversation, type Session } from "./src/api";
import { clearStored, loadStored, store } from "./src/session";
import { ChatScreen } from "./src/screens/ChatScreen";
import { ConversationsScreen } from "./src/screens/ConversationsScreen";
import { SignInScreen } from "./src/screens/SignInScreen";
import { DEFAULT_BRAND, palette } from "./src/theme";

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

  async function handleSignedIn(base: string, next: Session) {
    setServer(base);
    setSession(next);
    await store({ server: base, token: next.token });
    setScreen({ name: "list" });
  }

  async function handleSignOut() {
    await clearStored();
    setSession(null);
    setServer("");
    setScreen({ name: "signIn" });
  }

  const brand = session?.branding.brand_color || DEFAULT_BRAND;

  return (
    <SafeAreaProvider>
    <View style={styles.root}>
      <StatusBar barStyle="light-content" backgroundColor={brand} />
      {screen.name === "loading" ? (
        <SafeAreaView style={styles.center}>
          <ActivityIndicator color={brand} />
        </SafeAreaView>
      ) : screen.name === "signIn" || !session ? (
        <SafeAreaView style={styles.flex}>
          <SignInScreen onSignedIn={handleSignedIn} />
        </SafeAreaView>
      ) : screen.name === "chat" ? (
        <ChatScreen
          server={server}
          session={session}
          conversation={screen.conversation}
          onBack={() => setScreen({ name: "list" })}
        />
      ) : (
        <ConversationsScreen
          server={server}
          session={session}
          onOpen={(conversation) => setScreen({ name: "chat", conversation })}
          onSignOut={handleSignOut}
        />
      )}
    </View>
    </SafeAreaProvider>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: palette.canvas },
  flex: { flex: 1 },
  center: { flex: 1, alignItems: "center", justifyContent: "center" },
});
