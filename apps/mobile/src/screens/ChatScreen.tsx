import { useCallback, useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  FlatList,
  KeyboardAvoidingView,
  Platform,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from "react-native";
import {
  getConversation,
  reply as sendReply,
  setMode,
  type Conversation,
  type Message,
  type Session,
} from "../api";
import { renderRichText } from "../rich";
import { contrastOn, palette, tint } from "../theme";

function timeLabel(iso: string): string {
  return new Date(iso).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}

/**
 * One conversation, with the takeover the portal already supports: while the
 * mode is "ai" the agent answers, and taking over pauses it so the business
 * replies itself. Sending is only possible after taking over, which mirrors
 * what the server enforces.
 */
export function ChatScreen({
  server,
  session,
  conversation,
  onBack,
}: {
  server: string;
  session: Session;
  conversation: Conversation;
  onBack: () => void;
}) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [mode, setLocalMode] = useState<"ai" | "human">(conversation.mode);
  const [loaded, setLoaded] = useState(false);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const listRef = useRef<FlatList<Message>>(null);
  const mounted = useRef(true);

  const brand = session.branding.brand_color;

  const load = useCallback(async () => {
    try {
      const detail = await getConversation(server, session, conversation.id);
      if (!mounted.current) return;
      setMessages(detail.messages || []);
      setLocalMode(detail.mode);
      setError(null);
    } catch (err) {
      if (mounted.current) setError(err instanceof Error ? err.message : "Could not load this conversation");
    } finally {
      if (mounted.current) setLoaded(true);
    }
  }, [server, session, conversation.id]);

  useEffect(() => {
    mounted.current = true;
    load();
    const timer = setInterval(load, 10000);
    return () => {
      mounted.current = false;
      clearInterval(timer);
    };
  }, [load]);

  async function toggleMode() {
    const next = mode === "human" ? "ai" : "human";
    setBusy(true);
    try {
      const detail = await setMode(server, session, conversation.id, next);
      if (mounted.current) {
        setLocalMode(detail.mode);
        setMessages(detail.messages || []);
      }
    } catch (err) {
      if (mounted.current) setError(err instanceof Error ? err.message : "Could not change the mode");
    } finally {
      if (mounted.current) setBusy(false);
    }
  }

  async function send() {
    const content = draft.trim();
    if (!content || busy || mode !== "human") return;
    setBusy(true);
    setDraft("");
    try {
      const detail = await sendReply(server, session, conversation.id, content);
      if (mounted.current) {
        setMessages(detail.messages || []);
        setError(null);
      }
    } catch (err) {
      if (mounted.current) {
        setDraft(content);
        setError(err instanceof Error ? err.message : "Could not send");
      }
    } finally {
      if (mounted.current) setBusy(false);
    }
  }

  return (
    <KeyboardAvoidingView
      style={styles.flex}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
      keyboardVerticalOffset={0}
    >
      <View style={[styles.header, { backgroundColor: brand }]}>
        <TouchableOpacity onPress={onBack} accessibilityRole="button" accessibilityLabel="Back">
          <Text style={[styles.back, { color: contrastOn(brand) }]}>‹</Text>
        </TouchableOpacity>
        <View style={styles.headerText}>
          <Text style={[styles.headerTitle, { color: contrastOn(brand) }]} numberOfLines={1}>
            {conversation.contact_name || conversation.title || "Conversation"}
          </Text>
          <Text style={[styles.headerSub, { color: contrastOn(brand) }]}>
            {mode === "human" ? "You are replying" : "The assistant is replying"}
          </Text>
        </View>
        <TouchableOpacity onPress={toggleMode} disabled={busy} accessibilityRole="button">
          <Text style={[styles.takeover, { color: contrastOn(brand) }]}>
            {mode === "human" ? "Hand back" : "Take over"}
          </Text>
        </TouchableOpacity>
      </View>

      {!loaded ? (
        <View style={styles.center}>
          <ActivityIndicator color={brand} />
        </View>
      ) : (
        <FlatList
          ref={listRef}
          data={messages}
          keyExtractor={(item) => item.id}
          contentContainerStyle={styles.messages}
          onContentSizeChange={() => listRef.current?.scrollToEnd({ animated: false })}
          ListEmptyComponent={
            <View style={styles.center}>
              <Text style={styles.emptyBody}>No messages in this conversation yet.</Text>
            </View>
          }
          renderItem={({ item }) => {
            const outgoing = item.role === "assistant";
            return (
              <View style={[styles.bubbleRow, outgoing ? styles.rowRight : styles.rowLeft]}>
                <View
                  style={[
                    styles.bubble,
                    outgoing ? { backgroundColor: brand } : { backgroundColor: palette.bubbleIn },
                  ]}
                >
                  {item.sender_name && outgoing ? (
                    <Text style={[styles.sender, { color: contrastOn(brand) }]}>{item.sender_name}</Text>
                  ) : null}
                  <Text style={[styles.bubbleText, { color: outgoing ? contrastOn(brand) : palette.ink }]}>
                    {item.content
                      ? renderRichText(item.content, { color: outgoing ? contrastOn(brand) : palette.ink })
                      : item.attachments?.length
                        ? "[attachment]"
                        : ""}
                  </Text>
                  <Text style={[styles.time, { color: outgoing ? contrastOn(brand) : palette.subtle }]}>
                    {timeLabel(item.created_at)}
                  </Text>
                </View>
              </View>
            );
          }}
        />
      )}

      {error ? <Text style={styles.error}>{error}</Text> : null}

      <View style={styles.composer}>
        {mode === "human" ? (
          <>
            <TextInput
              style={styles.input}
              value={draft}
              onChangeText={setDraft}
              placeholder="Write a reply…"
              placeholderTextColor={palette.subtle}
              multiline
            />
            <TouchableOpacity
              style={[styles.send, { backgroundColor: brand }, (!draft.trim() || busy) && styles.sendDisabled]}
              onPress={send}
              disabled={!draft.trim() || busy}
              accessibilityRole="button"
              accessibilityLabel="Send"
            >
              {busy ? (
                <ActivityIndicator color={contrastOn(brand)} size="small" />
              ) : (
                <Text style={[styles.sendText, { color: contrastOn(brand) }]}>Send</Text>
              )}
            </TouchableOpacity>
          </>
        ) : (
          <TouchableOpacity
            style={[styles.takeoverWide, { backgroundColor: tint(brand, 0.12) }]}
            onPress={toggleMode}
            disabled={busy}
            accessibilityRole="button"
          >
            <Text style={[styles.takeoverWideText, { color: brand }]}>
              Take over to reply yourself
            </Text>
          </TouchableOpacity>
        )}
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1, backgroundColor: palette.canvas },
  header: { paddingTop: 58, paddingBottom: 14, paddingHorizontal: 14, flexDirection: "row", alignItems: "center", gap: 10 },
  back: { fontSize: 32, lineHeight: 34, fontWeight: "300", width: 22 },
  headerText: { flex: 1, minWidth: 0 },
  headerTitle: { fontSize: 17, fontWeight: "700" },
  headerSub: { fontSize: 12, opacity: 0.8, marginTop: 2 },
  takeover: { fontSize: 13, fontWeight: "600", opacity: 0.95 },
  center: { paddingTop: 60, alignItems: "center", paddingHorizontal: 40 },
  emptyBody: { fontSize: 14, color: palette.muted, textAlign: "center" },
  messages: { padding: 14, gap: 8 },
  bubbleRow: { flexDirection: "row" },
  rowLeft: { justifyContent: "flex-start" },
  rowRight: { justifyContent: "flex-end" },
  bubble: { maxWidth: "82%", borderRadius: 16, paddingHorizontal: 13, paddingVertical: 9 },
  sender: { fontSize: 12, fontWeight: "600", opacity: 0.85, marginBottom: 2 },
  bubbleText: { fontSize: 15, lineHeight: 21 },
  time: { fontSize: 11, marginTop: 4, opacity: 0.7, textAlign: "right" },
  error: { paddingHorizontal: 16, paddingBottom: 6, fontSize: 13, color: palette.danger },
  composer: {
    flexDirection: "row",
    alignItems: "flex-end",
    gap: 10,
    padding: 12,
    paddingBottom: 28,
    backgroundColor: palette.surface,
    borderTopWidth: 1,
    borderTopColor: palette.line,
  },
  input: {
    flex: 1,
    minHeight: 44,
    maxHeight: 120,
    borderWidth: 1,
    borderColor: palette.line,
    borderRadius: 22,
    paddingHorizontal: 16,
    paddingTop: 12,
    paddingBottom: 12,
    fontSize: 15,
    color: palette.ink,
  },
  send: { height: 44, paddingHorizontal: 18, borderRadius: 22, alignItems: "center", justifyContent: "center" },
  sendDisabled: { opacity: 0.45 },
  sendText: { fontSize: 15, fontWeight: "600" },
  takeoverWide: { flex: 1, height: 46, borderRadius: 23, alignItems: "center", justifyContent: "center" },
  takeoverWideText: { fontSize: 15, fontWeight: "600" },
});
