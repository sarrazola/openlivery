import { useCallback, useEffect, useRef, useState } from "react";
import {
  ActivityIndicator, FlatList, KeyboardAvoidingView, Modal, Platform, Pressable,
  RefreshControl, ScrollView, StyleSheet, Text, TextInput, View,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import {
  ApiError, createContact, getContact, listChannels, listContactConversations, listContacts,
  listTemplates, startConversation, updateContact, type Contact, type ContactUpdate,
  type Conversation, type PortalChannel, type Session, type Template,
} from "../api";
import { useStrings } from "../i18n";
import { contactsStrings } from "../contactsStrings";
import { channelLabel, initialFor } from "../conversations";
import { contrastOn, readableBrand, tint, useColors, useIsDark } from "../theme";

const PAGE_SIZE = 40;
type Props = {
  server: string; session: Session; onOpenConversation: (conversation: Conversation) => void;
  onBack: () => void; onSessionExpired?: () => void;
};
type Panel = "contact" | "new" | "edit" | "start" | null;

/** A native contact directory sharing the portal's contact and case records. */
export function ContactsScreen({ server, session, onOpenConversation, onBack, onSessionExpired }: Props) {
  const s = contactsStrings();
  const common = useStrings();
  const colors = useColors();
  const insets = useSafeAreaInsets();
  const brand = readableBrand(session.branding.brand_color, useIsDark());
  const [items, setItems] = useState<Contact[]>([]);
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const [error, setError] = useState("");
  const [panel, setPanel] = useState<Panel>(null);
  const [selected, setSelected] = useState<Contact | null>(null);
  const [history, setHistory] = useState<Conversation[]>([]);
  const [channels, setChannels] = useState<PortalChannel[]>([]);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState("");
  const [busy, setBusy] = useState(false);
  const listGeneration = useRef(0);
  const detailGeneration = useRef(0);
  const offset = useRef(0);
  const paging = useRef(false);
  const saving = useRef(false);
  const mounted = useRef(true);
  const expired = useRef(onSessionExpired);
  expired.current = onSessionExpired;
  const nameOf = (contact: Contact) => contact.name.trim() || contact.phone || contact.email || s.unnamed;

  const errorMessage = useCallback((err: unknown, fallback: string) => {
    if (err instanceof ApiError && err.status === 401) expired.current?.();
    return err instanceof Error ? err.message : fallback;
  }, []);

  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; listGeneration.current += 1; detailGeneration.current += 1; };
  }, []);
  useEffect(() => { const timer = setTimeout(() => setQuery(search.trim()), 300); return () => clearTimeout(timer); }, [search]);

  const load = useCallback(async (signal?: AbortSignal) => {
    const generation = ++listGeneration.current;
    paging.current = false;
    setLoadingMore(false);
    try {
      const rows = await listContacts(server, session, { search: query, limit: PAGE_SIZE, offset: 0, signal });
      if (!mounted.current || generation !== listGeneration.current) return;
      setItems(rows); offset.current = rows.length; setHasMore(rows.length === PAGE_SIZE); setError("");
    } catch (err) {
      if (!signal?.aborted && mounted.current && generation === listGeneration.current) setError(errorMessage(err, s.loadFailed));
    } finally {
      if (mounted.current && generation === listGeneration.current) { setLoading(false); setRefreshing(false); }
    }
  }, [server, session, query, errorMessage, s.loadFailed]);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setItems([]); setHasMore(false);
    void load(controller.signal);
    return () => controller.abort();
  }, [load]);

  async function loadMore() {
    if (!hasMore || paging.current || loading || refreshing) return;
    paging.current = true; setLoadingMore(true);
    const generation = listGeneration.current;
    try {
      const rows = await listContacts(server, session, { search: query, limit: PAGE_SIZE, offset: offset.current });
      if (!mounted.current || generation !== listGeneration.current) return;
      setItems((previous) => [...new Map([...previous, ...rows].map((row) => [row.id, row])).values()]);
      offset.current += rows.length; setHasMore(rows.length === PAGE_SIZE); setError("");
    } catch (err) {
      if (mounted.current && generation === listGeneration.current) setError(errorMessage(err, s.loadFailed));
    } finally {
      if (mounted.current && generation === listGeneration.current) { paging.current = false; setLoadingMore(false); }
    }
  }

  async function openContact(contact: Contact) {
    setSelected(contact); setPanel("contact"); setHistory([]); setChannels([]); setDetailLoading(true); setDetailError("");
    const generation = ++detailGeneration.current;
    try {
      const [fresh, rows, lines] = await Promise.all([
        getContact(server, session, contact.id), listContactConversations(server, session, contact.id), listChannels(server, session),
      ]);
      if (!mounted.current || generation !== detailGeneration.current) return;
      setSelected(fresh); setHistory(rows); setChannels(lines.filter((line) => line.channel === "whatsapp" || line.channel === "whatsapp_cloud"));
    } catch (err) {
      if (mounted.current && generation === detailGeneration.current) setDetailError(errorMessage(err, s.loadFailed));
    } finally {
      if (mounted.current && generation === detailGeneration.current) setDetailLoading(false);
    }
  }

  function closePanel() {
    if (busy) return;
    detailGeneration.current += 1;
    setPanel(null); setDetailError("");
  }
  function openConversation(conversation: Conversation) {
    setPanel(null);
    onOpenConversation(conversation);
  }
  async function saveContact(patch: ContactUpdate) {
    if (busy || saving.current) return;
    saving.current = true; setBusy(true); setDetailError("");
    try {
      const saved = panel === "new"
        ? await createContact(server, session, { ...patch, phone: patch.phone || "" })
        : await updateContact(server, session, selected!.id, patch);
      if (!mounted.current) return;
      setSelected(saved); setPanel("contact");
      await Promise.all([load(), openContact(saved)]);
    } catch (err) {
      if (mounted.current) setDetailError(err instanceof ApiError && err.status === 409 ? s.duplicatePhone : errorMessage(err, s.saveFailed));
    } finally { saving.current = false; if (mounted.current) setBusy(false); }
  }

  const title = panel === "new" ? s.newContact : panel === "edit" ? s.edit : panel === "start" ? s.start : selected ? nameOf(selected) : "";

  return <View style={[styles.screen, { backgroundColor: colors.surface, paddingTop: insets.top }]}>
    <View style={styles.header}>
      <Pressable accessibilityRole="button" accessibilityLabel={s.back} onPress={onBack} style={styles.icon}><Ionicons name="chevron-back" size={25} color={brand} /></Pressable>
      <View style={styles.flex}><Text style={[styles.title, { color: colors.ink }]}>{s.title}</Text><Text style={[styles.subtitle, { color: colors.muted }]}>{s.subtitle}</Text></View>
      <Pressable accessibilityRole="button" accessibilityLabel={s.newContact} onPress={() => { setDetailError(""); setPanel("new"); }} style={[styles.icon, { backgroundColor: tint(brand) }]}><Ionicons name="person-add-outline" size={22} color={brand} /></Pressable>
    </View>
    <View style={[styles.search, { backgroundColor: colors.canvas }]}><Ionicons name="search" size={18} color={colors.muted} /><TextInput accessibilityLabel={s.search} placeholder={s.search} placeholderTextColor={colors.muted} value={search} onChangeText={setSearch} autoCorrect={false} returnKeyType="search" style={[styles.searchInput, { color: colors.ink }]} />{search.length > 0 && <Pressable accessibilityRole="button" accessibilityLabel={s.cancel} onPress={() => setSearch("")} style={styles.clear}><Ionicons name="close-circle" size={20} color={colors.muted} /></Pressable>}</View>
    {error.length > 0 && <View style={styles.errorBox}><Text accessibilityRole="alert" style={{ color: colors.danger }}>{error}</Text><Pressable onPress={() => { setRefreshing(true); void load(); }}><Text style={{ color: brand }}>{s.retry}</Text></Pressable></View>}
    <FlatList data={items} keyExtractor={(item) => item.id} keyboardShouldPersistTaps="handled" contentContainerStyle={[styles.list, !items.length && styles.grow]}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); void load(); }} tintColor={brand} />}
      onEndReached={() => void loadMore()} onEndReachedThreshold={0.4}
      ListFooterComponent={loadingMore ? <ActivityIndicator color={brand} style={styles.loading} /> : null}
      ListEmptyComponent={<View style={styles.empty}>{loading ? <ActivityIndicator color={brand} /> : <><Ionicons name="people-outline" size={46} color={colors.subtle} /><Text style={[styles.emptyTitle, { color: colors.ink }]}>{query ? s.noMatches : s.empty}</Text>{!query && <Text style={[styles.emptyHint, { color: colors.muted }]}>{s.emptyHint}</Text>}</>}</View>}
      renderItem={({ item }) => <Pressable onPress={() => void openContact(item)} accessibilityRole="button" style={({ pressed }) => [styles.contactRow, { borderBottomColor: colors.line, backgroundColor: pressed ? colors.pressed : colors.surface }]}>
        <View style={[styles.avatar, { backgroundColor: tint(brand) }]}><Text style={[styles.initial, { color: brand }]}>{initialFor(nameOf(item))}</Text></View>
        <View style={styles.flex}><Text numberOfLines={1} style={[styles.name, { color: colors.ink }]}>{nameOf(item)}</Text><Text numberOfLines={1} style={[styles.meta, { color: colors.muted }]}>{[item.phone, item.email].filter(Boolean).join(" · ")}</Text><Text style={[styles.meta, { color: colors.muted }]}>{item.conversation_count} {item.conversation_count === 1 ? s.conversation : s.conversations}{item.open_count > 0 ? ` · ${item.open_count} ${item.open_count === 1 ? s.openCase : s.openCases}` : ""}</Text></View>
        <Ionicons name="chevron-forward" size={18} color={colors.subtle} />
      </Pressable>} />
    <Modal visible={panel !== null} animationType="slide" presentationStyle="pageSheet" onRequestClose={closePanel}>
      <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={[styles.screen, { backgroundColor: colors.surface, paddingTop: Platform.OS === "android" ? insets.top : 12 }]}>
        <View style={[styles.modalHeader, { borderBottomColor: colors.line }]}>
          <Pressable accessibilityRole="button" onPress={() => { if (busy) return; if (panel === "edit" || panel === "start") { setDetailError(""); setPanel("contact"); } else closePanel(); }} disabled={busy} style={styles.cancel}><Text style={{ color: brand }}>{panel === "edit" || panel === "start" ? s.back : s.close}</Text></Pressable>
          <Text numberOfLines={1} style={[styles.modalTitle, { color: colors.ink }]}>{title}</Text><View style={styles.headerSpacer} />
        </View>
        {detailError.length > 0 && <View style={styles.errorBox}><Text accessibilityRole="alert" style={{ color: colors.danger }}>{detailError}</Text>{panel === "contact" && selected && <Pressable onPress={() => void openContact(selected)}><Text style={{ color: brand }}>{s.retry}</Text></Pressable>}</View>}
        {(panel === "new" || panel === "edit") && <ContactEditor key={panel === "new" ? "new" : selected?.id} contact={panel === "edit" ? selected : null} busy={busy} onSave={saveContact} brand={brand} />}
        {panel === "contact" && selected && <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={[styles.detail, { paddingBottom: insets.bottom + 24 }]}>
          <View style={styles.identity}><View style={[styles.largeAvatar, { backgroundColor: tint(brand) }]}><Text style={[styles.largeInitial, { color: brand }]}>{initialFor(nameOf(selected))}</Text></View><Text style={[styles.title, { color: colors.ink }]}>{nameOf(selected)}</Text>{selected.phone && <Text selectable style={[styles.detailText, { color: colors.muted }]}>{selected.phone}</Text>}{selected.email && <Text selectable style={[styles.detailText, { color: colors.muted }]}>{selected.email}</Text>}</View>
          <View style={styles.actions}><Action disabled={detailLoading || busy} label={s.edit} icon="create-outline" onPress={() => { setDetailError(""); setPanel("edit"); }} brand={brand} /><Action label={s.start} icon="chatbubble-ellipses-outline" onPress={() => { setDetailError(""); setPanel("start"); }} brand={brand} disabled={detailLoading || !selected.phone || !channels.length} /></View>
          {!selected.phone && <Text style={[styles.hint, { color: colors.muted }]}>{s.noPhone}</Text>}
          {!detailLoading && selected.phone && !channels.length && <Text style={[styles.hint, { color: colors.muted }]}>{s.noLine}</Text>}
          <Text style={[styles.sectionTitle, { color: colors.ink }]}>{s.notes}</Text><Text selectable style={[styles.detailText, { color: selected.notes ? colors.ink : colors.muted }]}>{selected.notes || s.noNotes}</Text>
          <Text style={[styles.sectionTitle, { color: colors.ink }]}>{s.history}</Text>
          {detailLoading ? <ActivityIndicator color={brand} /> : !history.length ? <Text style={{ color: colors.muted }}>{s.noHistory}</Text> : history.map((conversation) => <Pressable key={conversation.id} accessibilityRole="button" onPress={() => openConversation(conversation)} style={[styles.historyRow, { borderColor: colors.line, backgroundColor: colors.raised }]}>
            <View style={styles.historyTop}><Text style={[styles.badge, { color: conversation.status === "resolved" ? colors.muted : brand, backgroundColor: tint(brand, 0.08) }]}>{conversation.status === "resolved" ? s.resolved : conversation.mode === "ai" ? s.ai : s.human}</Text><Text style={[styles.meta, { color: colors.muted }]}>{new Date(conversation.created_at).toLocaleDateString()}</Text></View>
            <Text numberOfLines={2} style={[styles.detailText, { color: colors.ink }]}>{conversation.preview || s.noMessages}</Text><View style={styles.historyBottom}><Text style={[styles.meta, { color: colors.muted }]}>{channelLabel(conversation.channel, common)}</Text><Ionicons name="arrow-forward" color={brand} size={17} /></View>
          </Pressable>)}
        </ScrollView>}
        {panel === "start" && selected && <StartConversation contact={selected} channels={channels} history={history} server={server} session={session} brand={brand} busy={busy} setBusy={setBusy} onOpen={openConversation} onClearError={() => setDetailError("")} onError={(err) => setDetailError(errorMessage(err, s.sendFailed))} />}
      </KeyboardAvoidingView>
    </Modal>
  </View>;
}

function Action({ label, icon, onPress, brand, disabled = false }: { label: string; icon: keyof typeof Ionicons.glyphMap; onPress: () => void; brand: string; disabled?: boolean }) {
  return <Pressable accessibilityRole="button" accessibilityState={{ disabled }} disabled={disabled} onPress={onPress} style={[styles.action, { backgroundColor: tint(brand), opacity: disabled ? 0.4 : 1 }]}><Ionicons name={icon} size={20} color={brand} /><Text style={[styles.actionLabel, { color: brand }]}>{label}</Text></Pressable>;
}

function ContactEditor({ contact, busy, onSave, brand }: { contact: Contact | null; busy: boolean; onSave: (patch: ContactUpdate) => Promise<void>; brand: string }) {
  const s = contactsStrings(); const colors = useColors(); const insets = useSafeAreaInsets();
  const [name, setName] = useState(contact?.name || ""); const [phone, setPhone] = useState(contact?.phone || "");
  const [email, setEmail] = useState(contact?.email || ""); const [notes, setNotes] = useState(contact?.notes || ""); const [error, setError] = useState("");
  const input = [styles.input, { backgroundColor: colors.raised, borderColor: colors.line, color: colors.ink }];
  function submit() {
    const digits = phone.replace(/\D/g, "");
    // Existing web contacts can have no phone; editing notes must still work.
    if ((!contact || contact.phone || phone.trim()) && (digits.length < 7 || digits.length > 15)) { setError(s.invalidPhone); return; }
    if (email.trim() && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) { setError(s.invalidEmail); return; }
    setError("");
    void onSave({ name: name.trim(), ...(phone.trim() ? { phone: phone.trim() } : {}), email: email.trim() || null, notes: notes.trim() });
  }
  return <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={[styles.form, { paddingBottom: insets.bottom + 24 }]}>
    <Text style={[styles.label, { color: colors.ink }]}>{s.name}</Text><TextInput accessibilityLabel={s.name} style={input} value={name} onChangeText={setName} editable={!busy} maxLength={180} autoComplete="name" />
    <Text style={[styles.label, { color: colors.ink }]}>{s.phone}</Text><TextInput accessibilityLabel={s.phone} style={input} value={phone} onChangeText={setPhone} editable={!busy} maxLength={40} keyboardType="phone-pad" autoComplete="tel" /><Text style={[styles.hint, { color: colors.muted }]}>{s.phoneHint}</Text>
    <Text style={[styles.label, { color: colors.ink }]}>{s.email}</Text><TextInput accessibilityLabel={s.email} style={input} value={email} onChangeText={setEmail} editable={!busy} keyboardType="email-address" autoCapitalize="none" autoCorrect={false} autoComplete="email" />
    <Text style={[styles.label, { color: colors.ink }]}>{s.notes}</Text><TextInput accessibilityLabel={s.notes} style={[...input, styles.multiline]} value={notes} onChangeText={setNotes} editable={!busy} multiline maxLength={5000} /><Text style={[styles.hint, { color: colors.muted }]}>{s.notesHint}</Text>
    {error.length > 0 && <Text accessibilityRole="alert" style={{ color: colors.danger }}>{error}</Text>}
    <Pressable accessibilityRole="button" disabled={busy} onPress={submit} style={[styles.primary, { backgroundColor: brand, opacity: busy ? 0.5 : 1 }]}>{busy ? <ActivityIndicator color={contrastOn(brand)} /> : <Text style={[styles.primaryText, { color: contrastOn(brand) }]}>{s.save}</Text>}</Pressable>
  </ScrollView>;
}

function StartConversation({ contact, channels, history, server, session, brand, busy, setBusy, onOpen, onClearError, onError }: {
  contact: Contact; channels: PortalChannel[]; history: Conversation[]; server: string; session: Session; brand: string;
  busy: boolean; setBusy: (busy: boolean) => void; onOpen: (conversation: Conversation) => void; onClearError: () => void; onError: (error: unknown) => void;
}) {
  const s = contactsStrings(); const colors = useColors(); const insets = useSafeAreaInsets();
  const [channel, setChannel] = useState(channels[0]?.channel || ""); const [message, setMessage] = useState("");
  const [templates, setTemplates] = useState<Template[]>([]); const [template, setTemplate] = useState<Template | null>(null);
  const [values, setValues] = useState<string[]>([]); const [loading, setLoading] = useState(false); const [error, setError] = useState("");
  const active = useRef(true); const sending = useRef(false);
  const [templateAttempt, setTemplateAttempt] = useState(0);
  const [currentHistory, setCurrentHistory] = useState(history);
  const existing = currentHistory.find((row) => row.status === "open" && row.channel === channel);
  const input = [styles.input, { backgroundColor: colors.raised, borderColor: colors.line, color: colors.ink }];
  const approved = channel === "whatsapp_cloud";
  const supported = channels.find((line) => line.channel === channel)?.supports_templates;
  useEffect(() => { active.current = true; return () => { active.current = false; }; }, []);
  useEffect(() => {
    let current = true;
    setError(""); onClearError(); setTemplate(null); setValues([]); setTemplates([]);
    if (!approved || !supported) { setLoading(false); return; }
    setLoading(true);
    listTemplates(server, session).then((rows) => { if (current) setTemplates(rows.filter((row) => row.status === "APPROVED")); })
      .catch((err) => { if (current) { setError(err instanceof Error ? err.message : s.loadFailed); onError(err); } })
      .finally(() => { if (current) setLoading(false); });
    return () => { current = false; };
  }, [channel, server, session, supported, templateAttempt]);
  async function send() {
    if (busy || sending.current || existing || !contact.phone) return;
    if (approved && (!template || values.length !== template.variables || values.some((value) => !value.trim()))) return;
    if (!approved && !message.trim()) return;
    sending.current = true; setBusy(true); setError(""); onClearError();
    try {
      const conversation = await startConversation(server, session, contact.id, approved
        ? { channel: "whatsapp_cloud", template: { name: template!.name, language: template!.language, variables: values.map((value) => value.trim()) } }
        : { channel: "whatsapp", text: message.trim() });
      if (active.current) onOpen(conversation);
    } catch (err) {
      if (active.current) { setError(err instanceof Error ? err.message : s.sendFailed); onError(err); }
      // Another operator may have started a case since this contact was opened.
      // Refresh the case list so the existing thread becomes reachable here.
      if (err instanceof ApiError && err.status === 409 && active.current) {
        try { const rows = await listContactConversations(server, session, contact.id); if (active.current) setCurrentHistory(rows); }
        catch { /* Keep the original delivery error and the unsent draft. */ }
      }
    }
    finally { sending.current = false; setBusy(false); }
  }
  const valid = !existing && !busy && (approved ? template && values.length === template.variables && values.every((value) => value.trim()) : message.trim());
  return <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={[styles.form, { paddingBottom: insets.bottom + 24 }]}>
    <Text style={[styles.label, { color: colors.ink }]}>{s.chooseLine}</Text>
    {channels.map((line) => <Pressable key={line.channel} disabled={busy} accessibilityRole="radio" accessibilityState={{ selected: channel === line.channel }} onPress={() => setChannel(line.channel)} style={[styles.lineChoice, { borderColor: line.channel === channel ? brand : colors.line, backgroundColor: line.channel === channel ? tint(brand, 0.08) : colors.surface }]}><Ionicons name={line.channel === channel ? "radio-button-on" : "radio-button-off"} size={22} color={brand} /><View style={styles.flex}><Text style={[styles.name, { color: colors.ink }]}>{line.channel === "whatsapp_cloud" ? "WhatsApp Business" : "WhatsApp"}</Text><Text style={[styles.meta, { color: colors.muted }]}>{[line.display_name, line.phone_number].filter(Boolean).join(" · ")}</Text></View></Pressable>)}
    {existing ? <><Text style={[styles.hint, { color: colors.muted }]}>{s.existing}</Text><Action label={s.open} icon="chatbubble-outline" onPress={() => onOpen(existing)} brand={brand} /></> : <>
      <Text style={[styles.hint, { color: colors.muted }]}>{approved ? s.templateHint : s.startHint}</Text>
      {approved ? <>
        <Text style={[styles.label, { color: colors.ink }]}>{s.templates}</Text>
        {loading ? <ActivityIndicator color={brand} /> : !templates.length ? <Text style={{ color: colors.muted }}>{s.noTemplates}</Text> : templates.map((row) => <Pressable key={`${row.name}:${row.language}`} disabled={busy} accessibilityRole="radio" accessibilityState={{ selected: template === row }} onPress={() => { setTemplate(row); setValues(Array(row.variables).fill("")); }} style={[styles.templateChoice, { borderColor: template === row ? brand : colors.line, backgroundColor: template === row ? tint(brand, 0.08) : colors.surface }]}><Text style={[styles.name, { color: colors.ink }]}>{row.name} · {row.language}</Text><Text numberOfLines={3} style={[styles.meta, { color: colors.muted }]}>{row.body}</Text></Pressable>)}
        {template && <>{values.map((value, index) => <View key={index}><Text style={[styles.label, { color: colors.ink }]}>{s.value} {index + 1}</Text><TextInput accessibilityLabel={`${s.value} ${index + 1}`} style={input} value={value} editable={!busy} onChangeText={(next) => setValues((previous) => previous.map((old, i) => i === index ? next : old))} /></View>)}<Text style={[styles.label, { color: colors.ink }]}>{s.preview}</Text><Text style={[styles.preview, { color: colors.ink, backgroundColor: colors.canvas }]}>{template.body.replace(/\{\{(\d+)\}\}/g, (match, index: string) => values[Number(index) - 1] || match)}{template.footer ? `\n\n${template.footer}` : ""}</Text></>}
      </> : <><Text style={[styles.label, { color: colors.ink }]}>{s.message}</Text><TextInput accessibilityLabel={s.message} style={[...input, styles.multiline]} value={message} onChangeText={setMessage} maxLength={4000} multiline editable={!busy} /></>}
      {error.length > 0 && <View style={{ gap: 8 }}><Text accessibilityRole="alert" style={{ color: colors.danger }}>{error}</Text>{approved && !templates.length && <Pressable accessibilityRole="button" disabled={loading || busy} onPress={() => setTemplateAttempt((value) => value + 1)} style={{ paddingVertical: 12 }}><Text style={{ color: brand }}>{s.retry}</Text></Pressable>}</View>}
      <Pressable accessibilityRole="button" disabled={!valid} onPress={() => void send()} style={[styles.primary, { backgroundColor: brand, opacity: valid ? 1 : 0.4 }]}>{busy ? <ActivityIndicator color={contrastOn(brand)} /> : <Text style={[styles.primaryText, { color: contrastOn(brand) }]}>{s.send}</Text>}</Pressable>
    </>}
  </ScrollView>;
}

const styles = StyleSheet.create({
  screen: { flex: 1 }, flex: { flex: 1 }, grow: { flexGrow: 1 }, header: { flexDirection: "row", alignItems: "center", padding: 18, gap: 12 },
  title: { fontSize: 28, fontWeight: "700", letterSpacing: -0.7 }, subtitle: { fontSize: 13, marginTop: 3 }, icon: { width: 44, height: 44, alignItems: "center", justifyContent: "center", borderRadius: 14 },
  search: { flexDirection: "row", alignItems: "center", marginHorizontal: 20, marginBottom: 12, paddingLeft: 14, borderRadius: 14 }, searchInput: { flex: 1, minHeight: 46, paddingHorizontal: 10, fontSize: 15 }, clear: { padding: 12 },
  list: { paddingHorizontal: 20, paddingBottom: 24 }, contactRow: { flexDirection: "row", alignItems: "center", gap: 12, minHeight: 96, paddingVertical: 17, borderBottomWidth: StyleSheet.hairlineWidth }, avatar: { width: 48, height: 48, borderRadius: 18, alignItems: "center", justifyContent: "center" }, initial: { fontSize: 20, fontWeight: "700" },
  name: { fontSize: 16, fontWeight: "600" }, meta: { fontSize: 12, marginTop: 4, lineHeight: 17 }, empty: { flex: 1, alignItems: "center", justifyContent: "center", padding: 30, gap: 14 }, emptyTitle: { fontSize: 20, fontWeight: "600", textAlign: "center" }, emptyHint: { fontSize: 15, lineHeight: 22, textAlign: "center" }, loading: { padding: 20 },
  errorBox: { margin: 16, gap: 10 }, modalHeader: { flexDirection: "row", alignItems: "center", borderBottomWidth: StyleSheet.hairlineWidth, minHeight: 58, paddingHorizontal: 12 }, cancel: { width: 66, minHeight: 44, justifyContent: "center", paddingLeft: 6 }, modalTitle: { flex: 1, fontSize: 17, fontWeight: "600", textAlign: "center" }, headerSpacer: { width: 66 }, detail: { padding: 22 }, identity: { alignItems: "center", gap: 8, paddingVertical: 16 }, largeAvatar: { width: 80, height: 80, borderRadius: 28, alignItems: "center", justifyContent: "center", marginBottom: 7 }, largeInitial: { fontSize: 34, fontWeight: "600" },
  detailText: { fontSize: 15, lineHeight: 23 }, actions: { flexDirection: "row", gap: 10, marginVertical: 18 }, action: { flex: 1, minHeight: 60, borderRadius: 14, alignItems: "center", justifyContent: "center", padding: 12, gap: 7 }, actionLabel: { fontSize: 13, fontWeight: "600", textAlign: "center" }, sectionTitle: { fontSize: 18, fontWeight: "600", marginTop: 24, marginBottom: 12 }, historyRow: { padding: 15, borderWidth: StyleSheet.hairlineWidth, borderRadius: 16, gap: 10, marginBottom: 12 }, historyTop: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" }, badge: { fontSize: 11, fontWeight: "600", paddingVertical: 5, paddingHorizontal: 9, borderRadius: 7 }, historyBottom: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  form: { padding: 22, gap: 8 }, label: { fontSize: 14, fontWeight: "600", marginTop: 12 }, input: { minHeight: 48, borderWidth: 1, borderRadius: 12, paddingHorizontal: 14, paddingVertical: 12, fontSize: 16 }, multiline: { minHeight: 120, textAlignVertical: "top" }, hint: { fontSize: 13, lineHeight: 20, marginBottom: 8 }, primary: { minHeight: 50, borderRadius: 14, alignItems: "center", justifyContent: "center", marginTop: 20, paddingHorizontal: 18 }, primaryText: { fontSize: 16, fontWeight: "600" }, lineChoice: { flexDirection: "row", alignItems: "center", borderWidth: 1, borderRadius: 14, padding: 14, gap: 12 }, templateChoice: { padding: 14, borderWidth: 1, borderRadius: 12 }, preview: { padding: 16, borderRadius: 14, fontSize: 15, lineHeight: 23 },
});
