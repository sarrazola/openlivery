import { useCallback, useEffect, useRef, useState } from "react";
import { ActivityIndicator, Alert, AppState, FlatList, KeyboardAvoidingView, Platform, Pressable, StyleSheet, Text, TextInput, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import {
  ApiError, assignConversation, getContact, getConversation, listCannedReplies, listContactConversations, listMembers, listTeams,
  markRead, reactToMessage, reply as sendReply, replyWithFile, replyWithTemplate, setConversationTeam, setMode, setStatus, updateContact,
  type CannedReply, type Contact, type Conversation, type ConversationDetail, type Message, type PortalMember, type Session, type Team,
} from "../api";
import { AttachmentView } from "../components/Attachments";
import { Composer, type OutgoingFile } from "../components/Composer";
import { TemplatePicker, ThreadAction, ThreadSheet } from "../components/ThreadSheets";
import { activityLabel, chatStrings } from "../chatStrings";
import { channelLabel, conversationName, initialFor, isWhatsApp, phoneFrom } from "../conversations";
import { useStrings, type Strings } from "../i18n";
import { acceptsAttachment, canQuoteMessage, canReactToMessage, canReply, channelCapabilities, deliveryPresentation, humanWindowOnly, interpolateCannedReply, isReplyWindowClosed, isSocialChannel } from "../inbox";
import { renderRichText } from "../rich";
import { contrastOn, readableBrand, tint, useColors, useIsDark } from "../theme";

function timeLabel(iso: string): string { return new Date(iso).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" }); }
function dayLabel(iso: string, s: Strings): string {
  const date = new Date(iso), now = new Date(), yesterday = new Date(now);
  yesterday.setDate(now.getDate() - 1);
  if (date.toDateString() === now.toDateString()) return s.when.today;
  if (date.toDateString() === yesterday.toDateString()) return s.when.yesterday;
  return date.toLocaleDateString(undefined, { day: "numeric", month: "long", ...(date.getFullYear() !== now.getFullYear() ? { year: "numeric" as const } : {}) });
}

type Props = {
  server: string; session: Session; conversation: Conversation; onBack: () => void;
  onConversationChange?: (conversation: ConversationDetail) => void;
  onOpenConversation?: (conversation: Conversation) => void;
  onSessionExpired?: () => void;
};

/** The portal's case lifecycle and permissions, presented as a native thread. */
export function ChatScreen({ server, session, conversation, onBack, onConversationChange, onOpenConversation, onSessionExpired }: Props) {
  const [detail, setDetail] = useState<ConversationDetail>({ ...conversation, messages: [] });
  const [loaded, setLoaded] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const errorSource = useRef<"load" | "action" | null>(null);
  const [sheet, setSheet] = useState<"details" | "assignee" | "team" | "media" | "canned" | null>(null);
  const [templateOpen, setTemplateOpen] = useState(false);
  const [quote, setQuote] = useState<Message | null>(null);
  const [messageAction, setMessageAction] = useState<Message | null>(null);
  const [members, setMembers] = useState<PortalMember[]>([]);
  const [teams, setTeams] = useState<Team[]>([]);
  const [contact, setContact] = useState<Contact | null>(null);
  const [contactName, setContactName] = useState("");
  const [contactEmail, setContactEmail] = useState("");
  const [contactNotes, setContactNotes] = useState("");
  const [history, setHistory] = useState<Conversation[]>([]);
  const [contextLoading, setContextLoading] = useState(false);
  const [contextError, setContextError] = useState<string | null>(null);
  const [canned, setCanned] = useState<CannedReply[]>([]);
  const [cannedQuery, setCannedQuery] = useState("");
  const [insertedReply, setInsertedReply] = useState<{ text: string; key: number } | null>(null);
  const consumeInsertedReply = useCallback((key: number) => {
    setInsertedReply((current) => current?.key === key ? null : current);
  }, []);
  const [hasNewMessages, setHasNewMessages] = useState(false);
  const [now, setNow] = useState(Date.now());
  const listRef = useRef<FlatList<Message>>(null);
  const mounted = useRef(true);
  const revision = useRef(0);
  const loading = useRef(false);
  const mutating = useRef(false);
  const nearBottom = useRef(true);
  const initialScrollPending = useRef(true);
  const scrollFrame = useRef<number | null>(null);
  const lastMessageId = useRef<string | undefined>(undefined);
  const readSignature = useRef<string | null>(null);
  const foreground = useRef(AppState.currentState === "active");
  const callbacks = useRef({ onConversationChange, onSessionExpired });
  callbacks.current = { onConversationChange, onSessionExpired };
  const colors = useColors(), s = useStrings(), c = chatStrings(), isDark = useIsDark(), insets = useSafeAreaInsets();
  const brand = readableBrand(session.branding.brand_color, isDark);
  const who = conversationName(detail, s);
  const resolved = detail.status === "resolved";
  const replyAllowed = loaded && canReply(detail, now);
  const windowClosed = isReplyWindowClosed(detail, now);
  const social = isSocialChannel(detail.channel);
  const contactPhone = contact?.phone || (isWhatsApp(detail.channel) ? phoneFrom(detail.external_chat_id) : null);
  const capabilities = channelCapabilities(detail);
  const socialBlockedHint = detail.reply_block_reason === "channel_disconnected" ? c.socialDisconnected : detail.reply_block_reason === "authorization_expired" ? c.socialAuthorization : detail.reply_block_reason === "another_app_controls_conversation" ? c.socialControl : c.socialWindowHint;

  const reportError = useCallback((err: unknown, source: "load" | "action" = "action") => {
    if (!mounted.current) return;
    if (err instanceof ApiError && err.status === 401) callbacks.current.onSessionExpired?.();
    errorSource.current = source;
    setError(err instanceof Error ? err.message : c.updateFailed);
  }, [c.updateFailed]);

  const scrollToLatest = useCallback(() => {
    if (scrollFrame.current !== null) cancelAnimationFrame(scrollFrame.current);
    // Content size can arrive before the viewport is laid out. One frame lets
    // FlatList finish measuring before the native scroll offset is requested.
    scrollFrame.current = requestAnimationFrame(() => {
      scrollFrame.current = null;
      if (mounted.current) listRef.current?.scrollToEnd({ animated: false });
    });
  }, []);

  const applyDetail = useCallback((next: ConversationDetail) => {
    if (!mounted.current) return;
    const nextId = next.messages.at(-1)?.id;
    if (lastMessageId.current && nextId !== lastMessageId.current && !nearBottom.current) setHasNewMessages(true);
    lastMessageId.current = nextId;
    setDetail(next);
    callbacks.current.onConversationChange?.(next);
  }, []);

  const load = useCallback(async (manual = false) => {
    if (loading.current || mutating.current || !foreground.current) return;
    loading.current = true;
    const generation = revision.current;
    if (manual) setRefreshing(true);
    try {
      const next = await getConversation(server, session, conversation.id);
      if (!mounted.current || generation !== revision.current) return;
      applyDetail(next);
      setLoaded(true);
      if (manual || errorSource.current === "load") { setError(null); errorSource.current = null; }
      // Reading activity alone must not generate another write every poll.
      const signature = `${next.id}:${next.last_inbound_at || next.created_at}`;
      if (readSignature.current !== signature) {
        await markRead(server, session, next.id);
        if (mounted.current) readSignature.current = signature;
      }
    } catch (err) { reportError(err, "load"); }
    finally {
      loading.current = false;
      if (mounted.current) setRefreshing(false);
    }
  }, [server, session, conversation.id, applyDetail, reportError]);

  useEffect(() => {
    mounted.current = true;
    void load();
    const timer = setInterval(() => { if (foreground.current) { setNow(Date.now()); void load(); } }, 5000);
    const subscription = AppState.addEventListener("change", (state) => {
      foreground.current = state === "active";
      if (foreground.current) { setNow(Date.now()); void load(); }
    });
    return () => { mounted.current = false; revision.current += 1; clearInterval(timer); subscription.remove(); if (scrollFrame.current !== null) cancelAnimationFrame(scrollFrame.current); };
  }, [load]);

  async function mutate(action: () => Promise<ConversationDetail>, sent = false): Promise<boolean> {
    if (mutating.current) return false;
    mutating.current = true; revision.current += 1; setBusy(true); setError(null);
    try {
      const next = await action();
      if (!mounted.current) return true;
      if (sent) { nearBottom.current = true; setHasNewMessages(false); }
      applyDetail(next);
      return true;
    } catch (err) { reportError(err); return false; }
    finally {
      mutating.current = false;
      if (mounted.current) { setBusy(false); setNow(Date.now()); }
    }
  }

  async function send(text: string): Promise<boolean> {
    if (!canReply(detail) || !channelCapabilities(detail).text || !text.trim()) return false;
    const success = await mutate(() => sendReply(server, session, detail.id, text, quote && canQuoteMessage(detail, quote) ? quote.id : undefined), true);
    if (success && mounted.current) setQuote(null);
    return success;
  }
  async function sendFile(file: OutgoingFile, caption: string): Promise<boolean> {
    if (!canReply(detail) || !acceptsAttachment(detail.channel, channelCapabilities(detail), file.type) || (caption.trim() && !channelCapabilities(detail).text)) return false;
    const success = await mutate(() => replyWithFile(server, session, detail.id, file, caption), true);
    if (success && mounted.current) setQuote(null);
    return success;
  }
  function resolve() {
    Alert.alert(c.resolveTitle, c.resolveHint, [
      { text: c.cancel, style: "cancel" },
      { text: c.resolveConfirm, onPress: () => { void mutate(() => setStatus(server, session, detail.id, "resolved")); } },
    ]);
  }

  async function loadContext() {
    setContextLoading(true); setContextError(null);
    const requests = [
      listMembers(server, session).then((data) => { if (mounted.current) setMembers(data); }),
      listTeams(server, session).then((data) => { if (mounted.current) setTeams(data); }),
    ];
    if (detail.contact_id) {
      requests.push(getContact(server, session, detail.contact_id).then((data) => {
        if (mounted.current) { setContact(data); setContactName(data.name); setContactEmail(data.email || ""); setContactNotes(data.notes); }
      }));
      requests.push(listContactConversations(server, session, detail.contact_id).then((data) => { if (mounted.current) setHistory(data.filter((item) => item.id !== detail.id)); }));
    }
    const result = await Promise.allSettled(requests);
    if (!mounted.current) return;
    const failure = result.find((item) => item.status === "rejected");
    if (failure?.status === "rejected") {
      if (failure.reason instanceof ApiError && failure.reason.status === 401) callbacks.current.onSessionExpired?.();
      setContextError(failure.reason instanceof Error ? failure.reason.message : c.loadFailed);
    }
    setContextLoading(false);
  }
  async function openCanned() {
    setSheet("canned"); setCannedQuery(""); setContextLoading(true); setContextError(null);
    try { const rows = await listCannedReplies(server, session); if (mounted.current) setCanned(rows); }
    catch (err) { if (mounted.current) setContextError(err instanceof Error ? err.message : c.loadFailed); }
    finally { if (mounted.current) setContextLoading(false); }
  }
  async function saveContact() {
    if (!contact || mutating.current) return;
    mutating.current = true; setBusy(true); setContextError(null);
    try {
      const saved = await updateContact(server, session, contact.id, { name: contactName.trim(), email: contactEmail.trim() || null, notes: contactNotes });
      if (mounted.current) { setContact(saved); setContactName(saved.name); setContactEmail(saved.email || ""); setContactNotes(saved.notes); }
    } catch (err) { if (mounted.current) setContextError(err instanceof Error ? err.message : c.updateFailed); }
    finally { mutating.current = false; if (mounted.current) { setBusy(false); void load(); } }
  }

  const sheetTitle = sheet === "assignee" ? c.assignee : sheet === "team" ? c.team : sheet === "media" ? c.shared : sheet === "canned" ? c.canned : c.details;
  const contactDirty = contact && (contactName !== contact.name || contactEmail !== (contact.email || "") || contactNotes !== contact.notes);
  return <KeyboardAvoidingView style={[styles.flex, { backgroundColor: colors.canvas }]} behavior={Platform.OS === "ios" ? "padding" : "height"}>
    <View style={[styles.header, { paddingTop: insets.top + 6, backgroundColor: colors.surface, borderBottomColor: colors.line }]}>
      <View style={styles.headerTop}>
        <Pressable onPress={onBack} style={styles.iconButton} hitSlop={8} accessibilityRole="button" accessibilityLabel={s.chat.back}><Ionicons name="chevron-back" size={28} color={brand} /></Pressable>
        <Pressable onPress={() => { setSheet("details"); void loadContext(); }} style={styles.identity} accessibilityRole="button" accessibilityLabel={`${c.details}: ${who}`}>
          <View style={[styles.avatar, { backgroundColor: tint(brand, .12) }]}><Text style={{ color: brand, fontSize: 18, fontWeight: "700" }}>{initialFor(who)}</Text></View>
          <View style={styles.flex}><Text numberOfLines={1} style={[styles.title, { color: colors.ink }]}>{who}</Text><Text numberOfLines={1} style={[styles.subtitle, { color: colors.muted }]}>{channelLabel(detail.channel, s)} · {resolved ? c.resolved : detail.mode === "ai" ? c.agent : detail.assignee_name || c.unassigned}</Text></View>
        </Pressable>
        <Pressable onPress={() => { setSheet("details"); void loadContext(); }} style={styles.iconButton} accessibilityRole="button" accessibilityLabel={c.details}><Ionicons name="ellipsis-horizontal" size={23} color={colors.muted} /></Pressable>
      </View>
      <View style={styles.toolbar}>
        <View style={[styles.badge, { backgroundColor: tint(resolved ? "#17876B" : brand, .10) }]}><Ionicons name={resolved ? "checkmark-circle-outline" : "chatbubble-ellipses-outline"} size={13} color={resolved ? "#17876B" : brand} /><Text style={{ color: resolved ? "#17876B" : brand, fontSize: 12, fontWeight: "600" }}>{resolved ? c.resolved : c.open}</Text></View>
        {detail.team_name ? <Text numberOfLines={1} style={[styles.teamName, { color: colors.muted }]}>{detail.team_name}</Text> : <View style={styles.flex} />}
        {!resolved ? <><Pressable onPress={() => { void mutate(() => setMode(server, session, detail.id, detail.mode === "human" ? "ai" : "human")); }} disabled={busy || !loaded} style={styles.toolbarButton} accessibilityRole="button"><Text style={{ color: brand, fontSize: 13, fontWeight: "600" }}>{detail.mode === "human" ? s.chat.handBack : s.chat.takeOver}</Text></Pressable><Pressable onPress={resolve} disabled={busy || !loaded} style={styles.toolbarButton} accessibilityRole="button" accessibilityLabel={c.resolve}><Ionicons name="checkmark-done-outline" size={21} color={brand} /></Pressable></> : null}
      </View>
    </View>
    {!loaded ? <View style={styles.center}>{error ? <Ionicons name="cloud-offline-outline" size={36} color={colors.muted} /> : <ActivityIndicator color={brand} />}</View> : <FlatList ref={listRef} data={detail.messages} keyExtractor={(item) => item.id} contentContainerStyle={styles.messages} keyboardDismissMode="interactive" keyboardShouldPersistTaps="handled" refreshing={refreshing} onRefresh={() => { void load(true); }}
      onScrollBeginDrag={() => {
        // An explicit gesture always takes precedence over the initial anchor.
        initialScrollPending.current = false;
        if (scrollFrame.current !== null) { cancelAnimationFrame(scrollFrame.current); scrollFrame.current = null; }
      }}
      onScroll={({ nativeEvent: { contentOffset, contentSize, layoutMeasurement } }) => {
        if (!layoutMeasurement.height || !contentSize.height) return;
        const atBottom = contentSize.height - contentOffset.y - layoutMeasurement.height < 100;
        // Native layout emits offset zero while the first scroll is pending.
        // It is not a user scrolling into history and must not drop the anchor.
        if (initialScrollPending.current && !atBottom) return;
        initialScrollPending.current = false;
        nearBottom.current = atBottom;
        if (atBottom) setHasNewMessages(false);
      }} scrollEventThrottle={100}
      onLayout={() => { if (initialScrollPending.current || nearBottom.current) scrollToLatest(); }}
      onContentSizeChange={() => { if (initialScrollPending.current || nearBottom.current) scrollToLatest(); }}
      ListEmptyComponent={<View style={styles.center}><Ionicons name="chatbubbles-outline" size={34} color={colors.subtle} /><Text style={[styles.empty, { color: colors.muted }]}>{s.chat.empty}</Text></View>}
      renderItem={({ item, index }) => {
        const previous = detail.messages[index - 1];
        const newDay = !previous || new Date(previous.created_at).toDateString() !== new Date(item.created_at).toDateString();
        const outgoing = item.role === "assistant";
        const ai = outgoing && item.sender_type === "ai";
        const bubbleColor = outgoing && !ai ? brand : ai ? tint(brand, isDark ? .23 : .12) : colors.bubbleIn;
        const textColor = outgoing && !ai ? contrastOn(brand) : colors.ink;
        const quoted = item.quoted_message_id ? detail.messages.find((message) => message.id === item.quoted_message_id) : null;
        const actionable = canQuoteMessage(detail, item, now) || canReactToMessage(detail, item);
        const delivery = deliveryPresentation(item.delivery_status);
        return <View>
          {newDay ? <View style={styles.dayRow}><Text style={[styles.day, { color: colors.muted, backgroundColor: colors.surface }]}>{dayLabel(item.created_at, s)}</Text></View> : null}
          {item.kind === "activity" ? <View style={styles.activity}><Text style={{ color: colors.muted, fontSize: 12, lineHeight: 18, textAlign: "center" }}>{activityLabel(item, c)} · {timeLabel(item.created_at)}</Text></View> : <View style={[styles.bubbleRow, { justifyContent: outgoing ? "flex-end" : "flex-start" }]}>
            <Pressable accessible={false} onLongPress={actionable && !busy ? () => setMessageAction(item) : undefined} style={[styles.bubble, { backgroundColor: bubbleColor, borderBottomRightRadius: outgoing ? 5 : 18, borderBottomLeftRadius: outgoing ? 18 : 5 }]}>
              <View style={styles.senderRow}><Text style={{ color: textColor, fontSize: 11, fontWeight: "700", opacity: .8, flex: 1 }}>{item.sender_name || (outgoing ? c.agent : who)}{ai ? ` · ${c.ai}` : ""}</Text>{actionable ? <Pressable onPress={() => setMessageAction(item)} disabled={busy} accessibilityRole="button" accessibilityLabel={c.actions} hitSlop={9}><Ionicons name="ellipsis-horizontal" size={17} color={textColor} /></Pressable> : null}</View>
              {item.quoted_message_id ? <View style={[styles.quoted, { borderLeftColor: textColor, backgroundColor: "rgba(127,127,127,.12)" }]}><Text numberOfLines={1} style={{ color: textColor, fontSize: 11, fontWeight: "700" }}>{quoted?.sender_name || (quoted?.role === "assistant" ? c.agent : who)}</Text><Text numberOfLines={3} style={{ color: textColor, fontSize: 12, marginTop: 3 }}>{quoted?.content || (quoted?.attachments?.length ? s.attachment.generic : c.unavailableQuote)}</Text></View> : null}
              {(item.attachments || []).map((attachment) => <View key={attachment.id} style={{ marginVertical: 4 }}><AttachmentView attachment={attachment} server={server} session={session} conversationId={detail.id} outgoing={outgoing && !ai} brand={brand} /></View>)}
              {item.content ? <Text style={[styles.messageText, { color: textColor }]}>{renderRichText(item.content, { color: textColor })}</Text> : null}
              <View style={styles.messageMeta}><Text style={{ color: textColor, opacity: .7, fontSize: 10 }}>{timeLabel(item.created_at)}</Text>{outgoing && (detail.channel === "whatsapp_cloud" || social) && delivery ? <View style={styles.delivery} accessibilityLabel={c[delivery.label]}><Ionicons name={delivery.icon} size={14} color={textColor} /><Text style={{ color: textColor, fontSize: 10, opacity: .8 }}>{c[delivery.label]}</Text></View> : null}</View>
              {item.delivery_error ? <Text style={{ color: textColor, fontSize: 11, marginTop: 5 }}>{item.delivery_error}</Text> : null}
              {item.reaction || item.incoming_reaction ? <View style={{ flexDirection: "row", gap: 5, marginTop: 5 }}>{item.reaction ? <Text style={[styles.reaction, { backgroundColor: colors.surface }]}>{item.reaction}</Text> : null}{item.incoming_reaction ? <Text style={[styles.reaction, { backgroundColor: colors.surface }]}>{item.incoming_reaction}</Text> : null}</View> : null}
            </Pressable>
          </View>}
        </View>;
      }} />}
    {hasNewMessages ? <Pressable style={[styles.latest, { backgroundColor: colors.surface, borderColor: colors.line }]} onPress={() => { nearBottom.current = true; setHasNewMessages(false); listRef.current?.scrollToEnd({ animated: true }); }} accessibilityRole="button" accessibilityLabel={c.latest}><Text style={{ color: brand, fontWeight: "600" }}>{c.newMessages}</Text><Ionicons name="arrow-down" size={16} color={brand} /></Pressable> : null}
    {error ? <View style={[styles.error, { backgroundColor: colors.surface }]}><Text accessibilityRole="alert" style={{ color: colors.danger, flex: 1, fontSize: 13 }}>{error}</Text><Pressable onPress={() => { void load(true); }} accessibilityRole="button" style={{ padding: 8 }}><Text style={{ color: brand, fontWeight: "600" }}>{c.retry}</Text></Pressable><Pressable onPress={() => setError(null)} accessibilityRole="button" accessibilityLabel={c.close} style={{ padding: 6 }}><Ionicons name="close" color={colors.muted} size={18} /></Pressable></View> : null}
    <View style={[styles.footer, { backgroundColor: colors.surface, borderTopColor: colors.line, paddingBottom: insets.bottom || 8 }]}>
      {quote && replyAllowed ? <View style={[styles.quoteBar, { borderLeftColor: brand }]}><View style={styles.flex}><Text style={{ color: brand, fontSize: 12, fontWeight: "700" }}>{c.quoting} {quote.sender_name || (quote.role === "assistant" ? c.agent : who)}</Text><Text numberOfLines={2} style={{ color: colors.muted, fontSize: 12 }}>{quote.content || s.attachment.generic}</Text></View><Pressable onPress={() => setQuote(null)} style={styles.iconButton} accessibilityRole="button" accessibilityLabel={c.cancelQuote}><Ionicons name="close" color={colors.muted} size={20} /></Pressable></View> : null}
      {resolved ? <View style={styles.locked}><Ionicons name="checkmark-circle-outline" size={22} color={brand} /><Text style={{ color: colors.muted, flex: 1, fontSize: 13, lineHeight: 19 }}>{c.resolvedHint}</Text></View> : !loaded ? null : detail.mode === "ai" ? <View style={{ padding: 12 }}><ThreadAction brand={brand} icon="hand-left-outline" filled label={s.chat.takeOverWide} disabled={busy} onPress={() => { void mutate(() => setMode(server, session, detail.id, "human")); }} /></View> : windowClosed ? <View style={{ padding: 14, gap: 10 }}><Text style={{ color: colors.ink, fontWeight: "700" }}>{social ? c.socialBlocked : c.windowClosed}</Text><Text style={{ color: colors.muted, lineHeight: 19, fontSize: 13 }}>{social ? socialBlockedHint : c.windowHint}</Text>{!social && capabilities.templates !== false && <ThreadAction brand={brand} filled icon="document-text-outline" label={c.sendTemplate} disabled={busy} onPress={() => setTemplateOpen(true)} />}</View> : <>{humanWindowOnly(detail, now) && <View style={{ padding: 12, gap: 4 }}><Text style={{ color: brand, fontWeight: "700" }}>{c.socialHumanOnly}</Text><Text style={{ color: colors.muted, fontSize: 12 }}>{c.socialHumanHint}</Text></View>}{detail.channel === "instagram" && <Text style={{ color: colors.muted, fontSize: 11, paddingHorizontal: 14, paddingTop: 6 }}>{c.socialLongText}</Text>}<Composer channel={detail.channel} capabilities={capabilities} draftKey={`${server}:${session.client_id}:${session.user_id || "legacy"}:${detail.id}`} brand={brand} busy={busy} onSendText={send} onSendFile={sendFile} insertedReply={insertedReply} onReplyInserted={consumeInsertedReply} onSavedReplies={() => { void openCanned(); }} onAttachmentSelected={() => setQuote(null)} onError={setError} /></>}
    </View>

    <ThreadSheet visible={sheet !== null} title={sheetTitle} onClose={() => { if (!busy) setSheet(null); }}>
      {contextLoading && sheet !== "media" ? <ActivityIndicator color={brand} style={{ padding: 16 }} /> : null}
      {sheet === "details" ? <>
        <View style={styles.profile}><View style={[styles.largeAvatar, { backgroundColor: tint(brand) }]}><Text style={{ color: brand, fontSize: 26, fontWeight: "700" }}>{initialFor(who)}</Text></View><Text style={{ color: colors.ink, fontSize: 20, fontWeight: "700", textAlign: "center" }}>{who}</Text><Text style={{ color: colors.muted }}>{channelLabel(detail.channel, s)} · {resolved ? c.resolved : c.open}</Text></View>
        <ThreadAction brand={brand} icon="person-outline" label={c.assignee} subtitle={detail.assignee_name || (detail.mode === "ai" ? c.agent : c.unassigned)} disabled={resolved || busy || contextLoading} onPress={() => setSheet("assignee")} />
        <ThreadAction brand={brand} icon="people-outline" label={c.team} subtitle={detail.team_name || c.noTeam} disabled={resolved || busy || contextLoading} onPress={() => setSheet("team")} />
        <ThreadAction brand={brand} icon="images-outline" label={c.shared} onPress={() => setSheet("media")} />
        {detail.channel === "whatsapp_cloud" && capabilities.templates !== false && detail.mode === "human" && !resolved ? <ThreadAction brand={brand} icon="document-text-outline" label={c.sendTemplate} disabled={busy} onPress={() => { setSheet(null); setTimeout(() => setTemplateOpen(true), 300); }} /> : null}
        {contact ? <View style={{ gap: 10, marginTop: 14 }}>
          <Text style={[styles.sectionLabel, { color: colors.ink }]}>{c.contact}</Text>
          <Text style={{ color: colors.muted }}>{c.phone}: {contactPhone || "–"}</Text>
          <Text style={[styles.fieldLabel, { color: colors.muted }]}>{c.name}</Text><TextInput value={contactName} onChangeText={setContactName} editable={!busy} accessibilityLabel={c.name} style={[styles.input, { color: colors.ink, borderColor: colors.line, backgroundColor: colors.canvas }]} />
          <Text style={[styles.fieldLabel, { color: colors.muted }]}>{c.email}</Text><TextInput value={contactEmail} onChangeText={setContactEmail} autoCapitalize="none" keyboardType="email-address" editable={!busy} accessibilityLabel={c.email} style={[styles.input, { color: colors.ink, borderColor: colors.line, backgroundColor: colors.canvas }]} />
          <Text style={[styles.fieldLabel, { color: colors.muted }]}>{c.notes}</Text><TextInput value={contactNotes} onChangeText={setContactNotes} multiline editable={!busy} accessibilityLabel={c.notes} style={[styles.input, { color: colors.ink, borderColor: colors.line, backgroundColor: colors.canvas, minHeight: 90, textAlignVertical: "top" }]} /><Text style={{ color: colors.muted, fontSize: 12, lineHeight: 18 }}>{c.notesHint}</Text>
          {contactDirty ? <ThreadAction brand={brand} filled label={c.save} disabled={busy} onPress={() => { void saveContact(); }} /> : null}
          <Text style={[styles.sectionLabel, { color: colors.ink }]}>{c.history}</Text>
          {history.length ? history.map((item) => <ThreadAction key={item.id} brand={brand} label={item.title || who} subtitle={`${item.status === "resolved" ? c.resolved : c.open} · ${new Date(item.created_at).toLocaleDateString()}${item.preview ? ` · ${item.preview.slice(0, 90)}` : ""}`} icon={item.status === "resolved" ? "checkmark-circle-outline" : "chatbubble-outline"} disabled={!onOpenConversation} onPress={() => { setSheet(null); onOpenConversation?.(item); }} />) : <Text style={{ color: colors.muted, fontSize: 13 }}>{c.noHistory}</Text>}
        </View> : contactPhone ? <Text style={{ color: colors.muted, padding: 12 }}>{c.phone}: {contactPhone}</Text> : null}
      </> : null}
      {sheet === "assignee" ? members.map((member) => <ThreadAction key={member.id} brand={brand} label={`${member.name || member.email}${member.id === session.user_id ? ` (${c.me})` : ""}`} subtitle={member.email} selected={detail.assignee_id === member.id} disabled={busy} onPress={async () => { if (await mutate(() => assignConversation(server, session, detail.id, member.id))) setSheet("details"); }} />) : null}
      {sheet === "team" ? <><ThreadAction brand={brand} label={c.noTeam} selected={!detail.team_id} disabled={busy} onPress={async () => { if (await mutate(() => setConversationTeam(server, session, detail.id, null))) setSheet("details"); }} />{teams.map((team) => <ThreadAction key={team.id} brand={brand} label={team.name} subtitle={team.description || undefined} selected={detail.team_id === team.id} disabled={busy} onPress={async () => { if (await mutate(() => setConversationTeam(server, session, detail.id, team.id))) setSheet("details"); }} />)}</> : null}
      {sheet === "media" ? detail.messages.some((message) => message.attachments?.length) ? detail.messages.flatMap((message) => (message.attachments || []).map((attachment) => <View key={attachment.id} style={[styles.mediaItem, { borderColor: colors.line, backgroundColor: colors.raised }]}><AttachmentView attachment={attachment} server={server} session={session} conversationId={detail.id} outgoing={false} brand={brand} /><Text style={{ color: colors.muted, fontSize: 11, marginTop: 9 }}>{new Date(message.created_at).toLocaleDateString()} · {timeLabel(message.created_at)}</Text></View>)) : <Text style={{ color: colors.muted, padding: 16 }}>{c.noMedia}</Text> : null}
      {sheet === "canned" ? <><TextInput value={cannedQuery} onChangeText={setCannedQuery} placeholder={c.searchReplies} placeholderTextColor={colors.subtle} accessibilityLabel={c.searchReplies} style={[styles.input, { color: colors.ink, borderColor: colors.line, backgroundColor: colors.canvas }]} />{canned.filter((item) => `${item.shortcut} ${item.content}`.toLowerCase().includes(cannedQuery.toLowerCase())).map((item) => <ThreadAction key={item.id} brand={brand} label={`/${item.shortcut}`} subtitle={item.content} onPress={() => { setInsertedReply({ key: Date.now(), text: interpolateCannedReply(item.content, { contact_name: detail.contact_name || detail.title, contact_phone: contactPhone || "", my_name: session.user_name, business_name: session.branding.client_name }) }); setSheet(null); }} />)}{!contextLoading && !canned.length ? <Text style={{ color: colors.muted, padding: 12, lineHeight: 21 }}>{c.noCanned}</Text> : null}</> : null}
      {contextError && sheet !== "media" ? <View><Text accessibilityRole="alert" style={{ color: colors.danger, paddingVertical: 10 }}>{contextError}</Text><ThreadAction brand={brand} label={c.retry} onPress={() => { void (sheet === "canned" ? openCanned() : loadContext()); }} /></View> : null}
      {error && busy === false && (sheet === "team" || sheet === "assignee") ? <Text accessibilityRole="alert" style={{ color: colors.danger, padding: 10 }}>{error}</Text> : null}
    </ThreadSheet>
    <ThreadSheet visible={Boolean(messageAction)} title={c.actions} onClose={() => setMessageAction(null)}>
      {messageAction ? <><Text numberOfLines={4} style={{ color: colors.muted, lineHeight: 20, padding: 8 }}>{messageAction.content || s.attachment.generic}</Text>{canQuoteMessage(detail, messageAction, now) ? <ThreadAction brand={brand} label={c.quote} icon="return-up-back-outline" onPress={() => { setQuote(messageAction); setMessageAction(null); }} /> : null}{canReactToMessage(detail, messageAction) ? <><Text style={[styles.sectionLabel, { color: colors.ink }]}>{c.react}</Text><View style={styles.emojis}>{["👍", "❤️", "😂", "😮", "😢", "🙏"].map((emoji) => <Pressable key={emoji} disabled={busy} onPress={() => { const target = messageAction; setMessageAction(null); void mutate(() => reactToMessage(server, session, detail.id, target.id, emoji)); }} accessibilityRole="button" accessibilityLabel={`${c.react} ${emoji}`} style={[styles.emoji, { backgroundColor: messageAction.reaction === emoji ? tint(brand) : colors.canvas }]}><Text style={{ fontSize: 25 }}>{emoji}</Text></Pressable>)}</View>{messageAction.reaction ? <ThreadAction brand={brand} label={c.removeReaction} onPress={() => { const target = messageAction; setMessageAction(null); void mutate(() => reactToMessage(server, session, detail.id, target.id, "")); }} /> : null}</> : null}</> : null}
    </ThreadSheet>
    <TemplatePicker externalError={error} visible={templateOpen} server={server} session={session} brand={brand} onClose={() => setTemplateOpen(false)} onSend={(payload) => detail.channel === "whatsapp_cloud" && capabilities.templates !== false && detail.mode === "human" && !resolved ? mutate(() => replyWithTemplate(server, session, detail.id, payload), true) : Promise.resolve(false)} />
  </KeyboardAvoidingView>;
}
const styles = StyleSheet.create({
  flex: { flex: 1 }, header: { borderBottomWidth: StyleSheet.hairlineWidth }, headerTop: { flexDirection: "row", alignItems: "center", gap: 2, paddingHorizontal: 6 }, iconButton: { width: 42, height: 44, alignItems: "center", justifyContent: "center" }, identity: { flex: 1, flexDirection: "row", gap: 10, alignItems: "center", minWidth: 0 }, avatar: { width: 40, height: 40, borderRadius: 14, alignItems: "center", justifyContent: "center" }, title: { fontSize: 17, fontWeight: "700", letterSpacing: -.2 }, subtitle: { fontSize: 12, marginTop: 3 },
  toolbar: { flexDirection: "row", alignItems: "center", gap: 9, paddingHorizontal: 17, paddingVertical: 8 }, badge: { flexDirection: "row", alignItems: "center", gap: 4, paddingHorizontal: 8, paddingVertical: 5, borderRadius: 8 }, teamName: { fontSize: 12, flex: 1 }, toolbarButton: { minHeight: 32, paddingHorizontal: 7, alignItems: "center", justifyContent: "center" }, center: { flex: 1, padding: 48, alignItems: "center", justifyContent: "center" }, empty: { textAlign: "center", lineHeight: 22, marginTop: 12 }, messages: { flexGrow: 1, paddingHorizontal: 14, paddingBottom: 18, paddingTop: 6 }, dayRow: { alignItems: "center", marginVertical: 17 }, day: { fontSize: 11, fontWeight: "600", paddingHorizontal: 12, paddingVertical: 5, borderRadius: 9, overflow: "hidden" }, activity: { alignSelf: "center", paddingVertical: 10, paddingHorizontal: 16, maxWidth: "95%" }, bubbleRow: { flexDirection: "row", marginVertical: 4 }, bubble: { maxWidth: "88%", borderRadius: 18, paddingHorizontal: 12, paddingTop: 9, paddingBottom: 6, minWidth: 94 }, senderRow: { flexDirection: "row", gap: 15, alignItems: "center", marginBottom: 5 }, messageText: { fontSize: 15, lineHeight: 22 }, messageMeta: { flexDirection: "row", justifyContent: "flex-end", gap: 5, alignItems: "center", marginTop: 5 }, delivery: { flexDirection: "row", alignItems: "center", gap: 3 }, quoted: { borderLeftWidth: 3, borderRadius: 5, padding: 8, marginBottom: 8 }, reaction: { fontSize: 15, paddingHorizontal: 7, paddingVertical: 2, borderRadius: 12, overflow: "hidden" }, latest: { flexDirection: "row", gap: 8, alignItems: "center", alignSelf: "center", paddingHorizontal: 14, paddingVertical: 10, borderRadius: 24, borderWidth: 1, marginBottom: 8 }, error: { flexDirection: "row", paddingHorizontal: 12, paddingVertical: 6, alignItems: "center", gap: 4 }, footer: { borderTopWidth: StyleSheet.hairlineWidth }, locked: { flexDirection: "row", gap: 10, alignItems: "center", padding: 17 }, quoteBar: { flexDirection: "row", marginHorizontal: 14, marginTop: 10, paddingLeft: 10, borderLeftWidth: 3, alignItems: "center" }, profile: { alignItems: "center", gap: 9, paddingBottom: 16 }, largeAvatar: { width: 70, height: 70, borderRadius: 24, alignItems: "center", justifyContent: "center" }, sectionLabel: { fontSize: 15, fontWeight: "700", marginTop: 14, marginBottom: 4 }, fieldLabel: { fontSize: 12, fontWeight: "600", marginBottom: -5 }, input: { padding: 12, fontSize: 15, borderWidth: 1, borderRadius: 10 }, mediaItem: { borderWidth: StyleSheet.hairlineWidth, borderRadius: 14, padding: 14, alignSelf: "stretch", alignItems: "flex-start" }, emojis: { flexDirection: "row", gap: 6, flexWrap: "wrap", marginVertical: 10 }, emoji: { borderRadius: 12, padding: 10 },
});
