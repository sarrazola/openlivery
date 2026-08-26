import { useCallback, useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  FlatList,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import {
  getConversation,
  reply as sendReply,
  replyWithFile,
  setMode,
  type Conversation,
  type Message,
  type Session,
} from "../api";
import { AttachmentView } from "../components/Attachments";
import { Composer, type OutgoingFile } from "../components/Composer";
import { renderRichText } from "../rich";
import { contrastOn, readableBrand, tint, useColors, useIsDark } from "../theme";

function timeLabel(iso: string): string {
  return new Date(iso).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}

function dayLabel(iso: string): string {
  const date = new Date(iso);
  const now = new Date();
  if (date.toDateString() === now.toDateString()) return "Today";
  const yesterday = new Date(now);
  yesterday.setDate(now.getDate() - 1);
  if (date.toDateString() === yesterday.toDateString()) return "Yesterday";
  return date.toLocaleDateString(undefined, { day: "numeric", month: "long" });
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
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const listRef = useRef<FlatList<Message>>(null);
  const mounted = useRef(true);
  const colors = useColors();
  const isDark = useIsDark();
  const insets = useSafeAreaInsets();

  const brand = readableBrand(session.branding.brand_color, isDark);

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

  async function send(text: string) {
    if (!text || busy || mode !== "human") return;
    setBusy(true);
    try {
      const detail = await sendReply(server, session, conversation.id, text);
      if (mounted.current) {
        setMessages(detail.messages || []);
        setError(null);
      }
    } catch (err) {
      if (mounted.current) setError(err instanceof Error ? err.message : "Could not send");
    } finally {
      if (mounted.current) setBusy(false);
    }
  }

  async function sendFile(file: OutgoingFile) {
    if (busy || mode !== "human") return;
    setBusy(true);
    try {
      const detail = await replyWithFile(server, session, conversation.id, file);
      if (mounted.current) {
        setMessages(detail.messages || []);
        setError(null);
      }
    } catch (err) {
      if (mounted.current) setError(err instanceof Error ? err.message : "Could not send that file");
    } finally {
      if (mounted.current) setBusy(false);
    }
  }

  return (
    <KeyboardAvoidingView
      style={[styles.flex, { backgroundColor: colors.canvas }]}
      behavior={Platform.OS === "ios" ? "padding" : "height"}
    >
      <View
        style={[
          styles.header,
          { paddingTop: insets.top + 6, backgroundColor: colors.surface, borderBottomColor: colors.line },
        ]}
      >
        <Pressable
          onPress={onBack}
          hitSlop={12}
          style={({ pressed }) => [styles.back, pressed && styles.pressed]}
          accessibilityRole="button"
          accessibilityLabel="Back"
        >
          <Text style={[styles.backGlyph, { color: brand }]}>‹</Text>
        </Pressable>
        <View style={styles.headerText}>
          <Text style={[styles.headerTitle, { color: colors.ink }]} numberOfLines={1}>
            {conversation.contact_name || conversation.title || "Conversation"}
          </Text>
          <Text style={[styles.headerSub, { color: colors.muted }]} numberOfLines={1}>
            {mode === "human" ? "You are replying" : "The assistant is replying"}
          </Text>
        </View>
        <Pressable
          onPress={toggleMode}
          disabled={busy}
          hitSlop={10}
          style={({ pressed }) => [pressed && styles.pressed, busy && styles.pressed]}
          accessibilityRole="button"
        >
          <Text style={[styles.takeover, { color: brand }]}>
            {mode === "human" ? "Hand back" : "Take over"}
          </Text>
        </Pressable>
      </View>

      {!loaded ? (
        <View style={styles.center}>
          <ActivityIndicator color={colors.muted} />
        </View>
      ) : (
        <FlatList
          ref={listRef}
          data={messages}
          keyExtractor={(item) => item.id}
          contentContainerStyle={styles.messages}
          keyboardDismissMode="interactive"
          onContentSizeChange={() => listRef.current?.scrollToEnd({ animated: false })}
          ListEmptyComponent={
            <View style={styles.center}>
              <Text style={[styles.emptyBody, { color: colors.muted }]}>
                No messages in this conversation yet.
              </Text>
            </View>
          }
          renderItem={({ item, index }) => {
            const outgoing = item.role === "assistant";
            const previous = messages[index - 1];
            const newDay =
              !previous || new Date(previous.created_at).toDateString() !== new Date(item.created_at).toDateString();
            const attachments = item.attachments || [];
            const onlyMedia = !item.content && attachments.length > 0;
            const bubbleColor = outgoing ? brand : colors.bubbleIn;
            const textColor = outgoing ? contrastOn(brand) : colors.ink;

            return (
              // A View rather than a fragment: FlatList treats a fragment's
              // children as an unkeyed list and warns about it.
              <View>
                {newDay ? (
                  <View style={styles.dayRow}>
                    <Text style={[styles.dayLabel, { color: colors.subtle, backgroundColor: colors.canvas }]}>
                      {dayLabel(item.created_at)}
                    </Text>
                  </View>
                ) : null}
                <View style={[styles.bubbleRow, outgoing ? styles.rowRight : styles.rowLeft]}>
                  <View
                    style={[
                      styles.bubble,
                      { backgroundColor: bubbleColor },
                      onlyMedia && styles.bubbleMedia,
                    ]}
                  >
                    {item.sender_name && outgoing ? (
                      <Text style={[styles.sender, { color: textColor }]}>{item.sender_name}</Text>
                    ) : null}

                    {attachments.map((attachment) => (
                      <View key={attachment.id} style={styles.attachmentSlot}>
                        <AttachmentView
                          attachment={attachment}
                          server={server}
                          session={session}
                          conversationId={conversation.id}
                          outgoing={outgoing}
                          brand={brand}
                        />
                      </View>
                    ))}

                    {item.content ? (
                      <Text style={[styles.bubbleText, { color: textColor }]}>
                        {renderRichText(item.content, { color: textColor })}
                      </Text>
                    ) : null}

                    <Text style={[styles.time, { color: textColor }, onlyMedia && styles.timeOnMedia]}>
                      {timeLabel(item.created_at)}
                    </Text>
                  </View>
                </View>
              </View>
            );
          }}
        />
      )}

      {error ? (
        <Text style={[styles.error, { color: colors.danger }]} onPress={() => setError(null)}>
          {error}
        </Text>
      ) : null}

      <View
        style={[
          styles.footer,
          { backgroundColor: colors.surface, borderTopColor: colors.line, paddingBottom: insets.bottom || 8 },
        ]}
      >
        {mode === "human" ? (
          <Composer brand={brand} busy={busy} onSendText={send} onSendFile={sendFile} />
        ) : (
          <Pressable
            onPress={toggleMode}
            disabled={busy}
            style={({ pressed }) => [
              styles.takeoverWide,
              { backgroundColor: tint(brand, isDark ? 0.22 : 0.12) },
              pressed && styles.pressed,
            ]}
            accessibilityRole="button"
          >
            <Text style={[styles.takeoverWideText, { color: brand }]}>Take over to reply yourself</Text>
          </Pressable>
        )}
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  header: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    paddingBottom: 10,
    paddingHorizontal: 10,
    borderBottomWidth: StyleSheet.hairlineWidth,
  },
  back: { width: 28, alignItems: "flex-start" },
  backGlyph: { fontSize: 32, lineHeight: 34, fontWeight: "300" },
  pressed: { opacity: 0.5 },
  headerText: { flex: 1, minWidth: 0 },
  headerTitle: { fontSize: 17, fontWeight: "600", letterSpacing: -0.2 },
  headerSub: { fontSize: 13, marginTop: 1 },
  takeover: { fontSize: 15, paddingHorizontal: 6 },
  center: { paddingTop: 60, alignItems: "center", paddingHorizontal: 40 },
  emptyBody: { fontSize: 15, textAlign: "center" },
  messages: { padding: 12, paddingBottom: 18, gap: 3 },
  dayRow: { alignItems: "center", marginVertical: 12 },
  dayLabel: {
    fontSize: 12,
    fontWeight: "600",
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 10,
    overflow: "hidden",
  },
  bubbleRow: { flexDirection: "row", marginTop: 3 },
  rowLeft: { justifyContent: "flex-start" },
  rowRight: { justifyContent: "flex-end" },
  bubble: { maxWidth: "82%", borderRadius: 18, paddingHorizontal: 12, paddingVertical: 8 },
  bubbleMedia: { padding: 4 },
  attachmentSlot: { marginBottom: 4 },
  sender: { fontSize: 12, fontWeight: "600", opacity: 0.85, marginBottom: 2 },
  bubbleText: { fontSize: 16, lineHeight: 21 },
  time: { fontSize: 11, marginTop: 3, opacity: 0.7, textAlign: "right" },
  timeOnMedia: { marginRight: 4, marginBottom: 2 },
  error: { paddingHorizontal: 16, paddingVertical: 8, fontSize: 14 },
  footer: { borderTopWidth: StyleSheet.hairlineWidth },
  takeoverWide: {
    margin: 10,
    height: 46,
    borderRadius: 23,
    alignItems: "center",
    justifyContent: "center",
  },
  takeoverWideText: { fontSize: 16, fontWeight: "600" },
});
