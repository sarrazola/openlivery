import { useCallback, useEffect, useRef, useState } from "react";
import {
  ActivityIndicator, KeyboardAvoidingView, Modal, Platform, Pressable, RefreshControl,
  ScrollView, StyleSheet, Switch, Text, TextInput, View,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import {
  ApiError, createTeam, getReport, listMembers, listTeams, setAvailability, updateTeam,
  type PortalMember, type PortalReport, type Session, type Team, type TeamUpdate,
} from "../api";
import { formatDuration, reportRange } from "../reports";
import { workspaceStrings } from "../workspaceStrings";
import { contrastOn, readableBrand, tint, useColors, useIsDark } from "../theme";

type Props = { server: string; session: Session; onBack: () => void; onSessionExpired?: () => void };
type Shared = Pick<Props, "server" | "session"> & { brand: string; handleError: (error: unknown) => string };
const CHANNELS = ["whatsapp", "whatsapp_cloud", "widget"] as const;

/** Teams and operational reports using the same portal permissions as the inbox. */
export function WorkspaceScreen({ server, session, onBack, onSessionExpired }: Props) {
  const s = workspaceStrings(); const colors = useColors(); const insets = useSafeAreaInsets();
  const brand = readableBrand(session.branding.brand_color, useIsDark());
  const [tab, setTab] = useState<"teams" | "reports">("teams");
  const expired = useRef(onSessionExpired); expired.current = onSessionExpired;
  const handleError = useCallback((error: unknown) => {
    if (error instanceof ApiError && error.status === 401) expired.current?.();
    return error instanceof Error ? error.message : s.loadFailed;
  }, [s.loadFailed]);
  return <View style={[styles.screen, { backgroundColor: colors.surface, paddingTop: insets.top }]}>
    <View style={styles.header}><Pressable accessibilityRole="button" accessibilityLabel={s.back} onPress={onBack} style={styles.icon}><Ionicons name="chevron-back" color={brand} size={25} /></Pressable><View style={styles.flex}><Text style={[styles.title, { color: colors.ink }]}>{s.title}</Text><Text style={[styles.meta, { color: colors.muted }]}>{s.subtitle}</Text></View></View>
    <View style={[styles.tabs, { backgroundColor: colors.canvas }]}>{(["teams", "reports"] as const).map((item) => <Pressable key={item} accessibilityRole="tab" accessibilityState={{ selected: tab === item }} onPress={() => setTab(item)} style={[styles.tab, { backgroundColor: tab === item ? colors.surface : "transparent" }]}><Ionicons name={item === "teams" ? "people-outline" : "bar-chart-outline"} size={17} color={tab === item ? brand : colors.muted} /><Text style={[styles.tabLabel, { color: tab === item ? brand : colors.muted }]}>{s[item]}</Text></Pressable>)}</View>
    {tab === "teams" ? <TeamsPanel server={server} session={session} brand={brand} handleError={handleError} /> : <ReportsPanel server={server} session={session} brand={brand} handleError={handleError} />}
  </View>;
}

function TeamsPanel({ server, session, brand, handleError }: Shared) {
  const s = workspaceStrings(); const colors = useColors(); const insets = useSafeAreaInsets();
  const [teams, setTeams] = useState<Team[]>([]); const [members, setMembers] = useState<PortalMember[]>([]);
  const [loading, setLoading] = useState(true); const [error, setError] = useState(""); const [refreshing, setRefreshing] = useState(false);
  const [editing, setEditing] = useState<Team | "new" | null>(null); const [saving, setSaving] = useState(false); const [saveError, setSaveError] = useState("");
  const [availabilityBusy, setAvailabilityBusy] = useState(false);
  const generation = useRef(0); const active = useRef(true); const mutating = useRef(false); const changingAvailability = useRef(false);
  useEffect(() => { active.current = true; return () => { active.current = false; generation.current += 1; }; }, []);
  const load = useCallback(async () => {
    if (changingAvailability.current) { setRefreshing(false); return; }
    const current = ++generation.current;
    try {
      const [groups, people] = await Promise.all([listTeams(server, session), listMembers(server, session)]);
      if (!active.current || current !== generation.current) return;
      setTeams(groups); setMembers(people); setError("");
    } catch (err) { if (active.current && current === generation.current) setError(handleError(err)); }
    finally { if (active.current && current === generation.current) { setLoading(false); setRefreshing(false); } }
  }, [server, session, handleError]);
  useEffect(() => { void load(); }, [load]);
  async function save(payload: TeamUpdate) {
    if (!editing || mutating.current) return;
    mutating.current = true; setSaving(true); setSaveError("");
    try {
      if (editing === "new") await createTeam(server, session, payload);
      else await updateTeam(server, session, editing.id, payload);
      if (!active.current) return;
      setEditing(null); await load();
    } catch (err) { if (active.current) setSaveError(err instanceof ApiError && err.status === 409 ? s.duplicateName : handleError(err)); }
    finally { mutating.current = false; if (active.current) setSaving(false); }
  }
  async function toggleAvailability(member: PortalMember) {
    if (changingAvailability.current) return;
    changingAvailability.current = true; generation.current += 1;
    setRefreshing(false); setAvailabilityBusy(true);
    try {
      const updated = await setAvailability(server, session, member.availability === "online" ? "away" : "online");
      if (!active.current) return;
      setMembers((rows) => rows.map((row) => row.id === updated.id ? updated : row));
      setTeams((rows) => rows.map((row) => ({ ...row, members: row.members.map((person) => person.id === updated.id ? updated : person) })));
      setError("");
    } catch (err) { if (active.current) setError(handleError(err)); }
    finally { changingAvailability.current = false; if (active.current) setAvailabilityBusy(false); }
  }
  const edit = (team: Team | "new") => { setSaveError(""); setEditing(team); };
  return <>
    <ScrollView refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); void load(); }} tintColor={brand} />} contentContainerStyle={[styles.content, { paddingBottom: insets.bottom + 24 }]}>
      {error.length > 0 && <ErrorNotice message={error} retry={() => void load()} brand={brand} />}
      <View style={styles.sectionHeader}><Text style={[styles.sectionTitle, { color: colors.ink }]}>{s.teams}</Text><Pressable accessibilityRole="button" onPress={() => edit("new")} style={[styles.smallButton, { backgroundColor: tint(brand) }]}><Ionicons name="add" color={brand} size={17} /><Text style={{ color: brand }}>{s.newTeam}</Text></Pressable></View>
      {loading ? <ActivityIndicator color={brand} style={styles.loading} /> : !teams.length ? <View style={[styles.card, { borderColor: colors.line }]}><Ionicons name="people-outline" size={32} color={colors.subtle} /><Text style={[styles.name, { color: colors.ink }]}>{s.noTeams}</Text><Text style={[styles.body, { color: colors.muted }]}>{s.noTeamsHint}</Text></View> : teams.map((team) => <Pressable key={team.id} accessibilityRole="button" accessibilityLabel={`${s.editTeam}: ${team.name}`} onPress={() => edit(team)} style={[styles.card, { borderColor: colors.line, backgroundColor: colors.raised }]}>
        <View style={styles.row}><Text style={[styles.name, styles.flex, { color: colors.ink }]}>{team.name}</Text>{team.is_default && <Text style={[styles.badge, { color: brand, backgroundColor: tint(brand) }]}>{s.defaultTeam}</Text>}<Ionicons name="create-outline" color={brand} size={18} /></View>
        {team.description.length > 0 && <Text style={[styles.body, { color: colors.muted }]}>{team.description}</Text>}
        <Text style={[styles.meta, { color: colors.muted }]}>{team.strategy === "least_busy" ? s.leastBusy : s.roundRobin} · {team.open_count} {s.open}{team.unassigned_count > 0 ? ` · ${team.unassigned_count} ${s.unassigned}` : ""}</Text>
        <View style={styles.wrap}>{team.members.length ? team.members.map((member) => <View key={member.id} style={[styles.personChip, { backgroundColor: colors.canvas }]}><View style={[styles.dot, { backgroundColor: member.availability === "online" ? "#16a571" : colors.subtle }]} /><Text style={[styles.small, { color: colors.ink }]}>{member.name || member.email}</Text></View>) : <Text style={{ color: colors.muted }}>{s.noMembers}</Text>}</View>
      </Pressable>)}
      <Text style={[styles.sectionTitle, { color: colors.ink, marginTop: 22 }]}>{s.people}</Text>
      {members.map((member) => <View key={member.id} style={[styles.personRow, { borderBottomColor: colors.line }]}><View style={[styles.dot, { backgroundColor: member.availability === "online" ? "#16a571" : colors.subtle }]} /><View style={styles.flex}><Text style={[styles.name, { color: colors.ink }]}>{member.name || member.email}{member.id === session.user_id ? ` · ${s.me}` : ""}</Text><Text style={[styles.meta, { color: colors.muted }]}>{member.availability === "online" ? s.online : s.away}</Text></View>{member.id === session.user_id && <Pressable accessibilityRole="button" accessibilityLabel={s.changeAvailability} disabled={availabilityBusy} onPress={() => void toggleAvailability(member)} style={styles.availability}>{availabilityBusy ? <ActivityIndicator color={brand} /> : <Text style={[styles.small, { color: brand }]}>{member.availability === "online" ? s.goAway : s.goOnline}</Text>}</Pressable>}</View>)}
    </ScrollView>
    <Modal visible={editing !== null} animationType="slide" presentationStyle="pageSheet" onRequestClose={() => { if (!saving) setEditing(null); }}>
      <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={[styles.screen, { backgroundColor: colors.surface, paddingTop: Platform.OS === "android" ? insets.top : 12 }]}>
        <View style={[styles.modalHeader, { borderBottomColor: colors.line }]}><Pressable disabled={saving} onPress={() => setEditing(null)} style={styles.cancel}><Text style={{ color: brand }}>{s.cancel}</Text></Pressable><Text style={[styles.modalTitle, { color: colors.ink }]}>{editing === "new" ? s.newTeam : s.editTeam}</Text><View style={{ width: 80 }} /></View>
        {saveError.length > 0 && <Text accessibilityRole="alert" style={[styles.error, { color: colors.danger }]}>{saveError}</Text>}
        {editing !== null && <TeamEditor key={editing === "new" ? "new" : editing.id} team={editing === "new" ? null : editing} members={members} brand={brand} saving={saving} onSave={save} />}
      </KeyboardAvoidingView>
    </Modal>
  </>;
}

function TeamEditor({ team, members, brand, saving, onSave }: { team: Team | null; members: PortalMember[]; brand: string; saving: boolean; onSave: (payload: TeamUpdate) => Promise<void> }) {
  const s = workspaceStrings(); const colors = useColors(); const insets = useSafeAreaInsets();
  const [name, setName] = useState(team?.name || ""); const [description, setDescription] = useState(team?.description || "");
  const [strategy, setStrategy] = useState<Team["strategy"]>(team?.strategy || "round_robin");
  const [channels, setChannels] = useState(team?.channels || []); const [memberIds, setMemberIds] = useState(team?.members.map((member) => member.id) || []); const [isDefault, setDefault] = useState(team?.is_default || false);
  const input = [styles.input, { color: colors.ink, borderColor: colors.line, backgroundColor: colors.raised }];
  const toggle = (rows: string[], value: string) => rows.includes(value) ? rows.filter((item) => item !== value) : [...rows, value];
  return <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={[styles.content, { paddingBottom: insets.bottom + 24 }]}>
    <Text style={[styles.label, { color: colors.ink }]}>{s.teamName}</Text><TextInput accessibilityLabel={s.teamName} style={input} value={name} onChangeText={setName} maxLength={120} editable={!saving} />
    <Text style={[styles.label, { color: colors.ink }]}>{s.description}</Text><TextInput accessibilityLabel={s.description} style={[...input, styles.multiline]} value={description} onChangeText={setDescription} maxLength={500} editable={!saving} multiline />
    <Text style={[styles.label, { color: colors.ink }]}>{s.strategy}</Text>
    {(["round_robin", "least_busy"] as const).map((value) => <Pressable key={value} disabled={saving} accessibilityRole="radio" accessibilityState={{ selected: strategy === value }} onPress={() => setStrategy(value)} style={[styles.choice, { borderColor: strategy === value ? brand : colors.line }]}><Ionicons name={strategy === value ? "radio-button-on" : "radio-button-off"} size={22} color={brand} /><View style={styles.flex}><Text style={[styles.name, { color: colors.ink }]}>{value === "round_robin" ? s.roundRobin : s.leastBusy}</Text><Text style={[styles.meta, { color: colors.muted }]}>{value === "round_robin" ? s.roundRobinHint : s.leastBusyHint}</Text></View></Pressable>)}
    <Text style={[styles.label, { color: colors.ink }]}>{s.members}</Text>
    {members.length ? members.map((member) => <Pressable key={member.id} disabled={saving} accessibilityRole="checkbox" accessibilityState={{ checked: memberIds.includes(member.id) }} onPress={() => setMemberIds((rows) => toggle(rows, member.id))} style={[styles.choice, { borderColor: colors.line }]}><Ionicons name={memberIds.includes(member.id) ? "checkbox" : "square-outline"} size={22} color={brand} /><View style={styles.flex}><Text style={[styles.name, { color: colors.ink }]}>{member.name || member.email}</Text><Text style={[styles.meta, { color: colors.muted }]}>{member.availability === "online" ? s.online : s.away}</Text></View></Pressable>) : <Text style={{ color: colors.muted }}>{s.noMembers}</Text>}
    <Text style={[styles.label, { color: colors.ink }]}>{s.channels}</Text><Text style={[styles.meta, { color: colors.muted }]}>{s.channelHint}</Text>
    {CHANNELS.map((channel) => <View key={channel} style={styles.switchRow}><Text style={[styles.body, { color: colors.ink }]}>{channel === "widget" ? s.web : channel === "whatsapp_cloud" ? "WhatsApp Business" : "WhatsApp"}</Text><Switch accessibilityLabel={channel === "widget" ? s.web : channel === "whatsapp_cloud" ? "WhatsApp Business" : "WhatsApp"} value={channels.includes(channel)} onValueChange={() => setChannels((rows) => toggle(rows, channel))} disabled={saving} trackColor={{ true: brand }} /></View>)}
    <View style={[styles.switchRow, { marginTop: 12 }]}><View style={styles.flex}><Text style={[styles.name, { color: colors.ink }]}>{s.defaultTeam}</Text><Text style={[styles.meta, { color: colors.muted }]}>{s.defaultHint}</Text></View><Switch accessibilityLabel={s.defaultTeam} value={isDefault} onValueChange={setDefault} disabled={saving} trackColor={{ true: brand }} /></View>
    <Pressable accessibilityRole="button" disabled={saving || !name.trim()} onPress={() => void onSave({ name: name.trim(), description: description.trim(), strategy, channels, is_default: isDefault, member_ids: memberIds })} style={[styles.primary, { backgroundColor: brand, opacity: saving || !name.trim() ? 0.45 : 1 }]}>{saving ? <ActivityIndicator color={contrastOn(brand)} /> : <Text style={[styles.primaryText, { color: contrastOn(brand) }]}>{s.save}</Text>}</Pressable>
  </ScrollView>;
}

function ReportsPanel({ server, session, brand, handleError }: Shared) {
  const s = workspaceStrings(); const colors = useColors(); const insets = useSafeAreaInsets();
  const [days, setDays] = useState<7 | 30>(7); const [channel, setChannel] = useState(""); const [team, setTeam] = useState("");
  const [teams, setTeams] = useState<Team[]>([]); const [report, setReport] = useState<PortalReport | null>(null);
  const [loading, setLoading] = useState(true); const [refreshing, setRefreshing] = useState(false); const [error, setError] = useState("");
  const [reload, setReload] = useState(0);
  const { from, to, tz_offset } = reportRange(days);
  useEffect(() => {
    let current = true;
    listTeams(server, session).then((rows) => { if (current) setTeams(rows); }).catch((err) => { if (current) setError(handleError(err)); });
    return () => { current = false; };
  }, [server, session, handleError, reload]);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setReport(null); setError("");
    getReport(server, session, { from, to, tz_offset, ...(channel ? { channel } : {}), ...(team ? { team_id: team } : {}), signal: controller.signal })
      .then((next) => { if (!controller.signal.aborted) setReport(next); })
      .catch((err) => { if (!controller.signal.aborted) setError(handleError(err)); })
      .finally(() => { if (!controller.signal.aborted) { setLoading(false); setRefreshing(false); } });
    return () => controller.abort();
  }, [server, session, from, to, tz_offset, channel, team, handleError, reload]);
  const refresh = () => { setRefreshing(true); setReload((value) => value + 1); };
  const utcMinutes = -tz_offset;
  const utc = `UTC${utcMinutes >= 0 ? "+" : "−"}${String(Math.floor(Math.abs(utcMinutes) / 60)).padStart(2, "0")}:${String(Math.abs(utcMinutes) % 60).padStart(2, "0")}`;
  const labelChannel = (value: string) => value === "widget" ? s.web : value === "whatsapp_cloud" ? "WhatsApp Business" : value === "whatsapp" ? "WhatsApp" : value;
  const metrics: [string, string | number][] = report ? [
    [s.started, report.started], [s.resolved, report.resolved], [s.openNow, report.open_now], [s.agentsOnline, report.agents_online],
    [s.inbound, report.inbound_messages], [s.humanReplies, report.human_replies], [s.aiReplies, report.ai_replies], [s.activeContacts, report.active_contacts],
    [s.firstReply, formatDuration(report.avg_first_reply_seconds, s)], [s.resolutionTime, formatDuration(report.avg_resolution_seconds, s)],
  ] : [];
  const maxDay = Math.max(1, ...(report?.by_day.map((day) => Math.max(day.started, day.resolved)) || []));
  return <ScrollView refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refresh} tintColor={brand} />} contentContainerStyle={[styles.content, { paddingBottom: insets.bottom + 24 }]}>
    <View style={styles.wrap}>{([7, 30] as const).map((value) => <Pressable key={value} accessibilityRole="button" accessibilityState={{ selected: days === value }} onPress={() => setDays(value)} style={[styles.filter, { backgroundColor: days === value ? tint(brand) : colors.canvas }]}><Text style={{ color: days === value ? brand : colors.muted }}>{value === 7 ? s.days7 : s.days30}</Text></Pressable>)}</View>
    <Text style={[styles.meta, { color: colors.muted }]}>{from} → {to} · {s.localTime} · {utc}</Text>
    <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.filterRow}>{["", ...CHANNELS].map((value) => <Pressable key={value} accessibilityRole="button" accessibilityState={{ selected: channel === value }} onPress={() => setChannel(value)} style={[styles.filter, { backgroundColor: channel === value ? tint(brand) : colors.canvas }]}><Text style={{ color: channel === value ? brand : colors.muted }}>{value ? labelChannel(value) : s.allChannels}</Text></Pressable>)}</ScrollView>
    {teams.length > 0 && <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.filterRow}>{[{ id: "", name: s.allTeams }, ...teams].map((value) => <Pressable key={value.id} accessibilityRole="button" accessibilityState={{ selected: team === value.id }} onPress={() => setTeam(value.id)} style={[styles.filter, { backgroundColor: team === value.id ? tint(brand) : colors.canvas }]}><Text style={{ color: team === value.id ? brand : colors.muted }}>{value.name}</Text></Pressable>)}</ScrollView>}
    {error.length > 0 && <ErrorNotice message={error} retry={refresh} brand={brand} />}
    {loading ? <ActivityIndicator color={brand} style={styles.loading} /> : report && <>
      <View style={styles.metrics}>{metrics.map(([label, value]) => <View key={label} style={[styles.metric, { backgroundColor: colors.raised, borderColor: colors.line }]}><Text style={[styles.metricValue, { color: colors.ink }]}>{value}</Text><Text style={[styles.meta, { color: colors.muted }]}>{label}</Text></View>)}</View>
      <Text style={[styles.meta, { color: colors.muted }]}>{s.currentHint}</Text><Text style={[styles.meta, { color: colors.muted }]}>{s.averageHint}</Text>
      <Text style={[styles.sectionTitle, { color: colors.ink, marginTop: 24 }]}>{s.daily}</Text><Text style={[styles.meta, { color: colors.muted }]}>{s.started} / {s.resolved}</Text>
      {!report.started && !report.resolved ? <Text style={[styles.body, { color: colors.muted }]}>{s.noActivity}</Text> : report.by_day.map((day) => <View key={day.date} style={styles.dayRow} accessible accessibilityLabel={`${day.date}: ${s.started} ${day.started}, ${s.resolved} ${day.resolved}`}><Text style={[styles.dayLabel, { color: colors.muted }]}>{new Date(`${day.date}T12:00:00`).toLocaleDateString(undefined, { day: "numeric", month: "short" })}</Text><View style={styles.flex}><View style={[styles.bar, { width: `${day.started / maxDay * 100}%`, backgroundColor: brand }]} /><View style={[styles.bar, { width: `${day.resolved / maxDay * 100}%`, backgroundColor: "#16a571" }]} /></View><Text style={[styles.dayCount, { color: colors.ink }]}>{day.started} / {day.resolved}</Text></View>)}
      <Text style={[styles.sectionTitle, { color: colors.ink, marginTop: 24 }]}>{s.channelActivity}</Text>
      {report.by_channel.length ? report.by_channel.map((row) => <View key={row.channel} style={[styles.statRow, { borderBottomColor: colors.line }]}><Text style={{ color: colors.ink }}>{labelChannel(row.channel)}</Text><Text style={[styles.name, { color: brand }]}>{row.started}</Text></View>) : <Text style={{ color: colors.muted }}>{s.noActivity}</Text>}
      <Text style={[styles.sectionTitle, { color: colors.ink, marginTop: 24 }]}>{s.teamActivity}</Text>
      {report.by_agent.map((member, index) => <View key={`${index}:${member.name}`} style={[styles.card, { borderColor: colors.line }]}><Text style={[styles.name, { color: colors.ink }]}>{member.name || s.people}</Text><Text style={[styles.meta, { color: colors.muted }]}>{s.replies}: {member.replies} · {s.assigned}: {member.assigned} · {s.openNow}: {member.open_now}</Text></View>)}
    </>}
  </ScrollView>;
}

function ErrorNotice({ message, retry, brand }: { message: string; retry: () => void; brand: string }) {
  const s = workspaceStrings(); const colors = useColors();
  return <View style={styles.errorNotice}><Text accessibilityRole="alert" style={{ color: colors.danger }}>{message}</Text><Pressable accessibilityRole="button" onPress={retry}><Text style={{ color: brand }}>{s.retry}</Text></Pressable></View>;
}

const styles = StyleSheet.create({
  screen: { flex: 1 }, flex: { flex: 1 }, header: { flexDirection: "row", alignItems: "center", padding: 18, gap: 12 }, title: { fontSize: 28, fontWeight: "700", letterSpacing: -0.7 }, icon: { width: 40, height: 44, alignItems: "center", justifyContent: "center" }, meta: { fontSize: 12, lineHeight: 18, marginTop: 4 },
  tabs: { flexDirection: "row", borderRadius: 14, padding: 4, marginHorizontal: 20, marginBottom: 8 }, tab: { flex: 1, flexDirection: "row", gap: 8, alignItems: "center", justifyContent: "center", minHeight: 40, borderRadius: 11 }, tabLabel: { fontSize: 14, fontWeight: "600" }, content: { padding: 20, gap: 12 }, row: { flexDirection: "row", alignItems: "center", gap: 10 }, sectionHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 10 }, sectionTitle: { fontSize: 19, fontWeight: "600" }, smallButton: { flexDirection: "row", alignItems: "center", gap: 6, padding: 11, borderRadius: 12 }, loading: { padding: 30 },
  card: { borderRadius: 16, padding: 16, borderWidth: StyleSheet.hairlineWidth, gap: 9 }, name: { fontSize: 16, fontWeight: "600" }, body: { fontSize: 14, lineHeight: 22 }, badge: { fontSize: 10, paddingHorizontal: 7, paddingVertical: 4, borderRadius: 6 }, wrap: { flexDirection: "row", flexWrap: "wrap", gap: 8 }, personChip: { flexDirection: "row", gap: 6, paddingHorizontal: 8, paddingVertical: 6, alignItems: "center", borderRadius: 8 }, dot: { width: 7, height: 7, borderRadius: 4 }, small: { fontSize: 12 }, personRow: { flexDirection: "row", alignItems: "center", gap: 12, borderBottomWidth: StyleSheet.hairlineWidth, paddingVertical: 14 }, availability: { maxWidth: 130, minHeight: 44, justifyContent: "center", paddingHorizontal: 8 },
  modalHeader: { flexDirection: "row", alignItems: "center", minHeight: 58, borderBottomWidth: StyleSheet.hairlineWidth }, cancel: { width: 80, minHeight: 44, paddingLeft: 18, justifyContent: "center" }, modalTitle: { flex: 1, textAlign: "center", fontSize: 17, fontWeight: "600" }, error: { marginHorizontal: 20, marginTop: 16 }, label: { fontSize: 14, fontWeight: "600", marginTop: 8 }, input: { minHeight: 48, borderWidth: 1, borderRadius: 12, padding: 13, fontSize: 16 }, multiline: { minHeight: 80, textAlignVertical: "top" }, choice: { borderWidth: 1, borderRadius: 12, padding: 12, flexDirection: "row", alignItems: "center", gap: 12 }, switchRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 12, paddingVertical: 8 }, primary: { minHeight: 50, borderRadius: 14, alignItems: "center", justifyContent: "center", marginTop: 16 }, primaryText: { fontSize: 16, fontWeight: "600" },
  filter: { borderRadius: 10, paddingVertical: 10, paddingHorizontal: 14 }, filterRow: { gap: 8 }, metrics: { flexDirection: "row", flexWrap: "wrap", gap: 10, marginTop: 8 }, metric: { flexGrow: 1, flexBasis: "46%", borderWidth: StyleSheet.hairlineWidth, borderRadius: 16, padding: 16, minHeight: 94 }, metricValue: { fontSize: 24, fontWeight: "700", letterSpacing: -0.5 }, dayRow: { flexDirection: "row", alignItems: "center", gap: 10, paddingVertical: 2 }, dayLabel: { width: 52, fontSize: 11 }, dayCount: { width: 48, fontSize: 11, textAlign: "right" }, bar: { height: 5, borderRadius: 3, marginVertical: 2 }, statRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingVertical: 12, borderBottomWidth: StyleSheet.hairlineWidth }, errorNotice: { gap: 12, paddingVertical: 10 },
});
