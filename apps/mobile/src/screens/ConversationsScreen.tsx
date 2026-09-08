import { useCallback, useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  AppState,
  FlatList,
  Modal,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { Image } from "expo-image";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import {
  ApiError,
  assetUrl,
  getInboxSummary,
  listConversations,
  listMembers,
  listTeams,
  setAvailability,
  type Conversation,
  type Session,
  type Team,
  type InboxSummary,
} from "../api";
import { conversationTimestamp, mergeConversationPages } from "../inbox";
import { channelIcon, channelLabel, conversationName, initialFor } from "../conversations";
import { useStrings, type Strings } from "../i18n";
import { readableBrand, tint, useColors, useIsDark } from "../theme";

type Folder = "all" | "unread" | "mine" | "ai";
const PAGE_SIZE = 40;
function whenLabel(iso: string, s: Strings): string {
  const date = new Date(iso);
  if (!Number.isFinite(date.getTime())) return "";
  const now = new Date();
  if (date.toDateString() === now.toDateString())
    return date.toLocaleTimeString(undefined, {
      hour: "numeric",
      minute: "2-digit",
    });
  now.setDate(now.getDate() - 1);
  if (date.toDateString() === now.toDateString()) return s.when.yesterday;
  return date.toLocaleDateString(undefined, { day: "numeric", month: "short" });
}

export function ConversationsScreen({
  server,
  session,
  onOpen,
  onSignOut,
  onSessionExpired,
  active = true,
}: {
  server: string;
  session: Session;
  onOpen: (conversation: Conversation) => void;
  onSignOut: () => void;
  onSessionExpired?: () => void;
  active?: boolean;
}) {
  const [items, setItems] = useState<Conversation[]>([]);
  const [summary, setSummary] = useState<InboxSummary | null>(null);
  const [teams, setTeams] = useState<Team[]>([]);
  const [status, setStatus] = useState<"open" | "resolved">("open");
  const [folder, setFolder] = useState<Folder>("all");
  const [team, setTeam] = useState("");
  const [channel, setChannel] = useState("");
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [sheet, setSheet] = useState<"filters" | "account" | null>(null);
  const [availability, updateAvailability] = useState<"online" | "away">(
    "away",
  );
  const [availabilityBusy, setAvailabilityBusy] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const generation = useRef(0);
  const requestId = useRef(0);
  const fetching = useRef(false);
  const controller = useRef<AbortController | null>(null);
  // Offset counts rows consumed from the API, including overlapping rows.
  const nextOffset = useRef(0);
  const mounted = useRef(true);
  const activeRef = useRef(active);
  activeRef.current = active;
  const s = useStrings();
  const colors = useColors();
  const isDark = useIsDark();
  const insets = useSafeAreaInsets();
  const brand = readableBrand(session.branding.brand_color, isDark);
  const logo = assetUrl(
    server,
    session.branding.client_logo_url || session.branding.agency_logo_url,
  );
  const onExpired = useRef(onSessionExpired);
  onExpired.current = onSessionExpired;

  useEffect(() => {
    const timer = setTimeout(() => setQuery(search.trim()), 300);
    return () => clearTimeout(timer);
  }, [search]);
  useEffect(() => {
    let active = true;
    Promise.all([listTeams(server, session), listMembers(server, session)])
      .then(([nextTeams, members]) => {
        if (!active) return;
        setTeams(nextTeams);
        const me = members.find((member) => member.id === session.user_id);
        if (me) updateAvailability(me.availability);
      })
      .catch((err) => {
        if (active && err instanceof ApiError && err.status === 401)
          onExpired.current?.();
      });
    return () => {
      active = false;
    };
  }, [server, session]);

  const load = useCallback(
    async (append = false, force = false) => {
      if (fetching.current && !force) return;
      if (force) controller.current?.abort();
      const abort = new AbortController();
      controller.current = abort;
      const id = ++requestId.current;
      const version = generation.current;
      fetching.current = true;
      if (append) setLoadingMore(true);
      try {
        const offset = append ? nextOffset.current : 0;
        const target = Math.max(PAGE_SIZE, nextOffset.current);
        // Refresh every loaded row so changed assignments and resolved cases disappear.
        const limit = append
          ? PAGE_SIZE
          : Math.min(target, 200);
        const rows = await listConversations(server, session, {
          status,
          ...(folder === "ai" ? { mode: "ai" as const } : {}),
          ...(folder === "mine" ? { assignee: "me" as const } : {}),
          ...(folder === "unread" ? { unread: true } : {}),
          search: query || undefined,
          team: team || undefined,
          channel: channel || undefined,
          limit,
          offset,
          signal: abort.signal,
        });
        let exhausted = rows.length < limit;
        if (!append && !exhausted && target > limit) {
          while (rows.length < target) {
            const nextLimit = Math.min(200, target - rows.length);
            const next = await listConversations(server, session, {
              status,
              ...(folder === "ai" ? { mode: "ai" as const } : {}),
              ...(folder === "mine" ? { assignee: "me" as const } : {}),
              ...(folder === "unread" ? { unread: true } : {}),
              search: query || undefined,
              team: team || undefined,
              channel: channel || undefined,
              limit: nextLimit,
              offset: rows.length,
              signal: abort.signal,
            });
            rows.push(...next);
            exhausted = next.length < nextLimit;
            if (exhausted) break;
          }
        }
        if (
          !mounted.current ||
          version !== generation.current ||
          id !== requestId.current
        )
          return;
        nextOffset.current = offset + rows.length;
        setItems((previous) => mergeConversationPages(append ? previous : [], rows));
        setHasMore(!exhausted);
        setError(null);
        getInboxSummary(server, session)
          .then((next) => {
            if (
              mounted.current &&
              version === generation.current &&
              id === requestId.current
            )
              setSummary(next);
          })
          .catch(() => {});
      } catch (err) {
        if (
          !mounted.current ||
          abort.signal.aborted ||
          version !== generation.current ||
          id !== requestId.current
        )
          return;
        if (err instanceof ApiError && err.status === 401)
          onExpired.current?.();
        else setError(err instanceof Error ? err.message : s.list.loadFailed);
      } finally {
        if (
          mounted.current &&
          version === generation.current &&
          id === requestId.current
        ) {
          fetching.current = false;
          setLoaded(true);
          setRefreshing(false);
          setLoadingMore(false);
        }
      }
    },
    [server, session, status, folder, query, team, channel, s.list.loadFailed],
  );

  useEffect(() => {
    mounted.current = true;
    generation.current += 1;
    nextOffset.current = 0;
    setItems([]);
    setLoaded(false);
    setHasMore(false);
    setError(null);
    void load(false, true);
    const timer = setInterval(() => {
      if (activeRef.current && AppState.currentState === "active") void load();
    }, 8000);
    const subscription = AppState.addEventListener("change", (state) => {
      if (activeRef.current && state === "active") void load(false, true);
    });
    return () => {
      mounted.current = false;
      generation.current += 1;
      controller.current?.abort();
      clearInterval(timer);
      subscription.remove();
    };
  }, [load]);

  useEffect(() => {
    if (active && mounted.current) void load(false, true);
  }, [active, load]);

  async function toggleAvailability() {
    if (availabilityBusy) return;
    setAvailabilityBusy(true);
    try {
      const result = await setAvailability(
        server,
        session,
        availability === "online" ? "away" : "online",
      );
      updateAvailability(result.availability);
    } catch (err) {
      Alert.alert(
        s.errors.generic,
        err instanceof Error ? err.message : s.errors.generic,
      );
    } finally {
      setAvailabilityBusy(false);
    }
  }
  function clearFilters() {
    setSearch("");
    setQuery("");
    setFolder("all");
    setTeam("");
    setChannel("");
  }
  const tabs: Folder[] = [
    "all",
    "unread",
    ...(session.user_id ? ["mine" as const] : []),
    "ai",
  ];
  const filterActive = !!team || !!channel;

  return (
    <View style={[styles.flex, { backgroundColor: colors.surface }]}>
      <View
        style={[
          styles.header,
          { paddingTop: insets.top + 10, borderBottomColor: colors.line },
        ]}
      >
        {logo ? (
          <Image
            source={{ uri: logo }}
            style={styles.logo}
            contentFit="contain"
          />
        ) : (
          <View
            style={[
              styles.logo,
              styles.centered,
              { backgroundColor: tint(brand) },
            ]}
          >
            <Text style={{ color: brand, fontWeight: "700", fontSize: 19 }}>
              {initialFor(session.branding.client_name)}
            </Text>
          </View>
        )}
        <View style={styles.flex}>
          <Text
            style={[styles.business, { color: colors.muted }]}
            numberOfLines={1}
          >
            {session.branding.client_name}
          </Text>
          <Text style={[styles.title, { color: colors.ink }]}>
            {s.inbox.title}
          </Text>
        </View>
        <Pressable
          onPress={() => setSheet("account")}
          style={styles.iconButton}
          accessibilityRole="button"
          accessibilityLabel={s.inbox.account}
          testID="inbox-account"
        >
          <Ionicons name="person-circle-outline" size={29} color={brand} />
        </Pressable>
      </View>
      <View style={styles.controls}>
        <View style={[styles.search, { backgroundColor: colors.canvas }]}>
          <Ionicons name="search" size={18} color={colors.muted} />
          <TextInput
            value={search}
            onChangeText={setSearch}
            placeholder={s.inbox.search}
            placeholderTextColor={colors.muted}
            style={[styles.input, { color: colors.ink }]}
            autoCorrect={false}
            returnKeyType="search"
            accessibilityLabel={s.inbox.search}
            testID="inbox-search"
          />
          {search ? (
            <Pressable
              onPress={() => setSearch("")}
              accessibilityLabel={s.inbox.clearFilters}
              hitSlop={12}
            >
              <Ionicons name="close-circle" size={19} color={colors.muted} />
            </Pressable>
          ) : null}
        </View>
        <View style={styles.statusRow}>
          <View style={[styles.segment, { backgroundColor: colors.canvas }]}>
            {(["open", "resolved"] as const).map((value) => (
              <Pressable
                key={value}
                onPress={() => {
                  setStatus(value);
                  setFolder("all");
                }}
                accessibilityRole="tab"
                accessibilityState={{ selected: status === value }}
                testID={`inbox-${value}`}
                style={[
                  styles.segmentButton,
                  status === value && { backgroundColor: colors.surface },
                ]}
              >
                <Text
                  style={{
                    color: status === value ? colors.ink : colors.muted,
                    fontWeight: "600",
                    fontSize: 14,
                  }}
                >
                  {s.inbox[value]} {summary ? summary[value] : ""}
                </Text>
              </Pressable>
            ))}
          </View>
          <Pressable
            style={[
              styles.filterButton,
              {
                borderColor: filterActive ? brand : colors.line,
                backgroundColor: filterActive ? tint(brand) : colors.surface,
              },
            ]}
            onPress={() => setSheet("filters")}
            accessibilityRole="button"
            accessibilityLabel={s.inbox.filters}
          >
            <Ionicons name="options-outline" size={21} color={brand} />
          </Pressable>
        </View>
        {status === "open" && (
          <ScrollView
            horizontal
            showsHorizontalScrollIndicator={false}
            contentContainerStyle={styles.tabs}
          >
            {tabs.map((value) => {
              const count = value === "all" ? summary?.open : summary?.[value];
              return (
                <Pressable
                  key={value}
                  testID={`inbox-folder-${value}`}
                  onPress={() => setFolder(value)}
                  accessibilityRole="tab"
                  accessibilityState={{ selected: folder === value }}
                  style={[
                    styles.tab,
                    {
                      backgroundColor:
                        folder === value ? tint(brand) : colors.surface,
                    },
                  ]}
                >
                  <Text
                    style={{
                      color: folder === value ? brand : colors.muted,
                      fontWeight: "600",
                    }}
                  >
                    {s.inbox[value]}
                  </Text>
                  {!!count && (
                    <Text
                      style={[
                        styles.count,
                        { color: folder === value ? brand : colors.muted },
                      ]}
                    >
                      {count > 99 ? "99+" : count}
                    </Text>
                  )}
                </Pressable>
              );
            })}
          </ScrollView>
        )}
        {channel && <Pressable onPress={() => setChannel("")} style={styles.teamPill} accessibilityRole="button" accessibilityLabel={s.inbox.clearFilters}><Ionicons name={channelIcon(channel)} size={14} color={brand} /><Text style={{ color: brand }}>{channelLabel(channel, s)}</Text><Ionicons name="close" size={15} color={brand} /></Pressable>}
        {team && (
          <Pressable onPress={() => setTeam("")} style={styles.teamPill}>
            <Ionicons name="people-outline" size={14} color={brand} />
            <Text style={{ color: brand }}>
              {teams.find((row) => row.id === team)?.name || s.inbox.teams}
            </Text>
            <Ionicons name="close" size={15} color={brand} />
          </Pressable>
        )}
      </View>
      {error && (
        <Pressable
          onPress={() => void load(false, true)}
          style={[styles.error, { backgroundColor: tint(colors.danger) }]}
          accessibilityRole="button"
        >
          <Text style={{ color: colors.danger, flex: 1 }}>
            {items.length ? s.inbox.connectionError : error}
          </Text>
          <Text style={{ color: colors.danger, fontWeight: "700" }}>
            {s.inbox.retry}
          </Text>
        </Pressable>
      )}
      {!loaded ? (
        <View style={[styles.flex, styles.centered]}>
          <ActivityIndicator color={brand} />
        </View>
      ) : (
        <FlatList
          data={items}
          keyExtractor={(item) => item.id}
          keyboardShouldPersistTaps="handled"
          keyboardDismissMode="on-drag"
          contentContainerStyle={[
            !items.length && styles.emptyContainer,
            { paddingBottom: insets.bottom + 16 },
          ]}
          refreshControl={
            <RefreshControl
              refreshing={refreshing}
              tintColor={brand}
              onRefresh={() => {
                setRefreshing(true);
                void load(false, true);
              }}
            />
          }
          onEndReachedThreshold={0.4}
          onEndReached={() => {
            if (hasMore) void load(true);
          }}
          ItemSeparatorComponent={() => (
            <View
              style={[styles.separator, { backgroundColor: colors.line }]}
            />
          )}
          ListEmptyComponent={
            <View style={styles.empty}>
              <View
                style={[styles.emptyIcon, { backgroundColor: tint(brand) }]}
              >
                <Ionicons
                  name={
                    status === "resolved"
                      ? "checkmark-done-outline"
                      : "chatbubbles-outline"
                  }
                  size={30}
                  color={brand}
                />
              </View>
              <Text style={[styles.emptyTitle, { color: colors.ink }]}>
                {query || team || channel || folder !== "all"
                  ? s.inbox.noResults
                  : s.list.emptyTitle}
              </Text>
              <Text style={[styles.emptyBody, { color: colors.muted }]}>
                {query || team || channel || folder !== "all"
                  ? s.inbox.noResultsBody
                  : s.list.emptyBody}
              </Text>
              {!!(query || team || channel || folder !== "all") && (
                <Pressable onPress={clearFilters} style={styles.iconButton}>
                  <Text style={{ color: brand, fontWeight: "600" }}>
                    {s.inbox.clearFilters}
                  </Text>
                </Pressable>
              )}
            </View>
          }
          ListFooterComponent={
            hasMore ? (
              <Pressable
                onPress={() => void load(true)}
                style={styles.more}
                accessibilityRole="button"
              >
                {loadingMore ? (
                  <ActivityIndicator color={brand} />
                ) : (
                  <Text style={{ color: brand }}>{s.inbox.loadMore}</Text>
                )}
              </Pressable>
            ) : null
          }
          renderItem={({ item }) => {
            const name = conversationName(item, s);
            const unread = item.mode === "human" && item.unread_count > 0;
            const owner =
              item.mode === "ai"
                ? s.inbox.aiHandling
                : item.assignee_name || s.inbox.legacyHuman;
            return (
              <Pressable
                testID={`conversation-${item.id}`}
                onPress={() => onOpen(item)}
                style={({ pressed }) => [
                  styles.row,
                  {
                    backgroundColor: pressed
                      ? colors.pressed
                      : unread
                        ? tint(brand, 0.035)
                        : colors.surface,
                  },
                ]}
                accessibilityRole="button"
                accessibilityLabel={`${name}, ${owner}${unread ? `, ${s.inbox.unread}` : ""}`}
              >
                <View style={[styles.avatar, { backgroundColor: tint(brand) }]}>
                  <Text style={[styles.avatarText, { color: brand }]}>
                    {initialFor(name)}
                  </Text>
                  <View
                    style={[
                      styles.channelIcon,
                      { backgroundColor: colors.surface },
                    ]}
                  >
                    <Ionicons
                      name={
                        channelIcon(item.channel)
                      }
                      size={14}
                      color={
                        item.channel.startsWith("whatsapp")
                          ? "#16834b"
                          : colors.muted
                      }
                    />
                  </View>
                </View>
                <View style={styles.flex}>
                  <View style={styles.rowTop}>
                    <Text
                      numberOfLines={1}
                      style={[
                        styles.rowTitle,
                        {
                          color: colors.ink,
                          fontWeight: unread ? "800" : "600",
                        },
                      ]}
                    >
                      {name}
                    </Text>
                    <Text
                      style={[
                        styles.when,
                        { color: unread ? brand : colors.muted },
                      ]}
                    >
                      {whenLabel(conversationTimestamp(item), s)}
                    </Text>
                  </View>
                  <View style={styles.rowTop}>
                    <Text
                      style={[
                        styles.preview,
                        { color: unread ? colors.ink : colors.muted },
                      ]}
                      numberOfLines={2}
                    >
                      {item.preview || s.list.noMessages}
                    </Text>
                    {unread && (
                      <View style={[styles.unread, { backgroundColor: brand }]}>
                        <Text style={styles.unreadText}>
                          {item.unread_count > 99 ? "99+" : item.unread_count}
                        </Text>
                      </View>
                    )}
                  </View>
                  <View style={styles.rowMeta}>
                    <Ionicons
                      name={
                        item.status === "resolved"
                          ? "checkmark-circle-outline"
                          : item.mode === "ai"
                            ? "sparkles-outline"
                            : "person-outline"
                      }
                      size={12}
                      color={colors.muted}
                    />
                    <Text
                      style={[styles.meta, { color: colors.muted }]}
                      numberOfLines={1}
                    >
                      {item.status === "resolved" ? s.inbox.resolved : owner}
                      {item.team_name ? ` · ${item.team_name}` : ""}
                    </Text>
                    <Text style={[styles.channel, { color: colors.muted }]}>
                      {channelLabel(item.channel, s)}
                    </Text>
                  </View>
                </View>
              </Pressable>
            );
          }}
        />
      )}
      <Modal
        visible={sheet !== null}
        transparent
        animationType="slide"
        onRequestClose={() => setSheet(null)}
      >
        <View style={styles.modal}>
          <Pressable
            style={styles.backdrop}
            onPress={() => setSheet(null)}
            accessibilityLabel={s.inbox.cancel}
          />
          <View
            style={[
              styles.sheet,
              {
                backgroundColor: colors.surface,
                paddingBottom: insets.bottom + 20,
              },
            ]}
          >
            <View style={styles.sheetHeader}>
              <Text style={[styles.sheetTitle, { color: colors.ink }]}>
                {sheet === "filters" ? s.inbox.filters : s.inbox.account}
              </Text>
              <Pressable
                onPress={() => setSheet(null)}
                style={styles.iconButton}
              >
                <Text style={{ color: brand, fontWeight: "600" }}>
                  {s.inbox.done}
                </Text>
              </Pressable>
            </View>
            <ScrollView>
              {sheet === "filters" ? (
                <>
                <Text style={{ color: colors.muted, marginTop: 12 }}>{s.inbox.allChannels}</Text>
                {["", "whatsapp", "whatsapp_cloud", "instagram", "messenger", "widget"].map((value) => <Pressable key={value} style={styles.sheetRow} accessibilityRole="radio" accessibilityState={{ checked: channel === value }} onPress={() => setChannel(value)}><Text style={[styles.flex, { color: colors.ink, fontSize: 16 }]}>{value === "whatsapp_cloud" ? "WhatsApp Business" : value ? channelLabel(value, s) : s.inbox.allChannels}</Text>{channel === value && <Ionicons name="checkmark" size={22} color={brand} />}</Pressable>)}
                <Text style={{ color: colors.muted, marginTop: 12 }}>{s.inbox.teams}</Text>
                {[{ id: "", name: s.inbox.allTeams }, ...teams].map((row) => (
                  <Pressable
                    key={row.id}
                    onPress={() => {
                      setTeam(row.id);
                      setSheet(null);
                    }}
                    style={styles.sheetRow}
                    accessibilityRole="radio"
                    accessibilityState={{ checked: team === row.id }}
                  >
                    <Text
                      style={[styles.flex, { color: colors.ink, fontSize: 16 }]}
                    >
                      {row.name}
                    </Text>
                    {team === row.id && (
                      <Ionicons name="checkmark" size={22} color={brand} />
                    )}
                  </Pressable>
                ))}
                </>
              ) : (
                <>
                  <Text
                    style={{
                      color: colors.ink,
                      fontSize: 18,
                      fontWeight: "600",
                    }}
                  >
                    {session.user_name || session.branding.agency_name}
                  </Text>
                  <Text style={{ color: colors.muted, marginTop: 4 }}>
                    {session.branding.client_name}
                  </Text>
                  {!!session.user_id && (
                    <>
                      <Pressable
                        style={styles.sheetRow}
                        disabled={availabilityBusy}
                        onPress={toggleAvailability}
                        accessibilityRole="switch"
                        accessibilityState={{
                          checked: availability === "online",
                          disabled: availabilityBusy,
                        }}
                      >
                        <View
                          style={[
                            styles.dot,
                            {
                              backgroundColor:
                                availability === "online"
                                  ? "#16834b"
                                  : colors.subtle,
                            },
                          ]}
                        />
                        <Text
                          style={[
                            styles.flex,
                            { color: colors.ink, fontSize: 16 },
                          ]}
                        >
                          {
                            s.inbox[
                              availability === "online" ? "online" : "away"
                            ]
                          }
                        </Text>
                        {availabilityBusy ? (
                          <ActivityIndicator color={brand} />
                        ) : (
                          <Ionicons
                            name="swap-horizontal"
                            size={21}
                            color={brand}
                          />
                        )}
                      </Pressable>
                      <Text style={{ color: colors.muted, lineHeight: 21 }}>
                        {s.inbox.availabilityHint}
                      </Text>
                    </>
                  )}
                  <Pressable
                    style={[styles.sheetRow, { marginTop: 20 }]}
                    onPress={() =>
                      Alert.alert(s.inbox.signOutTitle, undefined, [
                        { text: s.inbox.cancel, style: "cancel" },
                        {
                          text: s.inbox.signOut,
                          style: "destructive",
                          onPress: () => {
                            setSheet(null);
                            onSignOut();
                          },
                        },
                      ])
                    }
                  >
                    <Ionicons
                      name="log-out-outline"
                      size={21}
                      color={colors.danger}
                    />
                    <Text style={{ color: colors.danger, fontSize: 16 }}>
                      {s.inbox.signOut}
                    </Text>
                  </Pressable>
                </>
              )}
            </ScrollView>
          </View>
        </View>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1, minWidth: 0 },
  centered: { alignItems: "center", justifyContent: "center" },
  header: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    paddingHorizontal: 20,
    paddingBottom: 16,
    borderBottomWidth: StyleSheet.hairlineWidth,
  },
  logo: { width: 43, height: 43, borderRadius: 13 },
  business: { fontSize: 12, marginBottom: 2 },
  title: { fontSize: 23, fontWeight: "700", letterSpacing: -0.5 },
  iconButton: {
    minHeight: 44,
    minWidth: 44,
    alignItems: "center",
    justifyContent: "center",
  },
  controls: { padding: 16, paddingBottom: 8, gap: 12 },
  search: {
    flexDirection: "row",
    alignItems: "center",
    gap: 9,
    borderRadius: 12,
    paddingHorizontal: 12,
  },
  input: { flex: 1, minWidth: 0, height: 44, fontSize: 14 },
  statusRow: { flexDirection: "row", gap: 10 },
  segment: { flex: 1, flexDirection: "row", padding: 3, borderRadius: 12 },
  segmentButton: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    paddingVertical: 10,
    borderRadius: 9,
  },
  filterButton: {
    width: 45,
    borderWidth: 1,
    borderRadius: 12,
    alignItems: "center",
    justifyContent: "center",
  },
  tabs: { gap: 4 },
  tab: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    paddingHorizontal: 12,
    minHeight: 40,
    borderRadius: 20,
  },
  count: { fontSize: 11, fontWeight: "700" },
  teamPill: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    paddingVertical: 4,
  },
  error: {
    marginHorizontal: 16,
    padding: 12,
    borderRadius: 10,
    flexDirection: "row",
    gap: 12,
  },
  emptyContainer: { flexGrow: 1, justifyContent: "center" },
  empty: { alignItems: "center", padding: 36 },
  emptyIcon: { padding: 20, borderRadius: 25, marginBottom: 18 },
  emptyTitle: { textAlign: "center", fontSize: 18, fontWeight: "600" },
  emptyBody: {
    marginTop: 8,
    fontSize: 15,
    lineHeight: 22,
    textAlign: "center",
  },
  separator: { height: StyleSheet.hairlineWidth, marginLeft: 83 },
  row: {
    flexDirection: "row",
    gap: 13,
    paddingHorizontal: 20,
    paddingVertical: 16,
  },
  avatar: {
    width: 48,
    height: 48,
    borderRadius: 18,
    alignItems: "center",
    justifyContent: "center",
  },
  avatarText: { fontSize: 19, fontWeight: "600" },
  channelIcon: {
    position: "absolute",
    bottom: -3,
    right: -4,
    padding: 3,
    borderRadius: 10,
  },
  rowTop: { flexDirection: "row", alignItems: "center", gap: 8 },
  rowTitle: { flex: 1, fontSize: 16 },
  when: { fontSize: 11 },
  preview: { flex: 1, fontSize: 14, lineHeight: 20, marginTop: 4 },
  unread: {
    minWidth: 20,
    height: 20,
    paddingHorizontal: 5,
    borderRadius: 10,
    alignItems: "center",
    justifyContent: "center",
  },
  unreadText: { color: "white", fontSize: 10, fontWeight: "700" },
  rowMeta: { flexDirection: "row", alignItems: "center", gap: 4, marginTop: 7 },
  meta: { flex: 1, fontSize: 11 },
  channel: { fontSize: 10 },
  more: { minHeight: 56, alignItems: "center", justifyContent: "center" },
  modal: { flex: 1, justifyContent: "flex-end" },
  backdrop: {
    position: "absolute",
    top: 0,
    right: 0,
    bottom: 0,
    left: 0,
    backgroundColor: "rgba(0,0,0,0.4)",
  },
  sheet: {
    borderTopLeftRadius: 24,
    borderTopRightRadius: 24,
    padding: 22,
    maxHeight: "75%",
  },
  sheetHeader: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    marginBottom: 12,
  },
  sheetTitle: { fontSize: 20, fontWeight: "700" },
  sheetRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    minHeight: 56,
  },
  dot: { width: 10, height: 10, borderRadius: 5 },
});
