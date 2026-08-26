import { useCallback, useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  FlatList,
  Platform,
  Pressable,
  RefreshControl,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { Image } from "expo-image";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { assetUrl, listConversations, type Conversation, type Session } from "../api";
import { useStrings, type Strings } from "../i18n";
import { contrastOn, readableBrand, tint, useColors, useIsDark } from "../theme";

function channelLabel(channel: string, s: Strings): string {
  if (channel === "whatsapp" || channel === "whatsapp_cloud") return s.channels.whatsapp;
  if (channel === "widget") return s.channels.widget;
  if (channel === "playground") return s.channels.playground;
  return channel;
}

function whenLabel(iso: string, s: Strings): string {
  const date = new Date(iso);
  const now = new Date();
  // Times and dates come from the phone's own formatting, so they follow its
  // locale without this file knowing anything about it.
  if (date.toDateString() === now.toDateString()) {
    return date.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
  }
  const yesterday = new Date(now);
  yesterday.setDate(now.getDate() - 1);
  if (date.toDateString() === yesterday.toDateString()) return s.when.yesterday;
  return date.toLocaleDateString(undefined, { day: "numeric", month: "short" });
}

/**
 * The list of conversations for this business.
 *
 * Polls while it is on screen, which is the honest option when the server has
 * no push provider configured: the interval is slower than the web inbox
 * because a phone pays for it in battery.
 *
 * The chrome is deliberately plain - a system-coloured bar, hairline
 * separators, the agency's colour carried by the accents rather than painted
 * over everything. A saturated header is the fastest way to make an app look
 * like a website someone wrapped.
 */
export function ConversationsScreen({
  server,
  session,
  onOpen,
  onSignOut,
}: {
  server: string;
  session: Session;
  onOpen: (conversation: Conversation) => void;
  onSignOut: () => void;
}) {
  const [items, setItems] = useState<Conversation[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const mounted = useRef(true);
  const colors = useColors();
  const s = useStrings();
  const isDark = useIsDark();
  const insets = useSafeAreaInsets();

  const brand = readableBrand(session.branding.brand_color, isDark);
  const logo = assetUrl(server, session.branding.client_logo_url || session.branding.agency_logo_url);

  const load = useCallback(async () => {
    try {
      const rows = await listConversations(server, session);
      if (mounted.current) {
        setItems(rows);
        setError(null);
      }
    } catch (err) {
      if (mounted.current) setError(err instanceof Error ? err.message : s.list.loadFailed);
    } finally {
      if (mounted.current) setLoaded(true);
    }
  }, [server, session]);

  useEffect(() => {
    mounted.current = true;
    load();
    const timer = setInterval(load, 15000);
    return () => {
      mounted.current = false;
      clearInterval(timer);
    };
  }, [load]);

  return (
    <View style={[styles.flex, { backgroundColor: colors.canvas }]}>
      <View
        style={[
          styles.header,
          { paddingTop: insets.top + 8, backgroundColor: colors.surface, borderBottomColor: colors.line },
        ]}
      >
        {logo ? (
          <Image source={{ uri: logo }} style={styles.logo} contentFit="contain" />
        ) : (
          <View style={[styles.logoFallback, { backgroundColor: tint(brand, 0.16) }]}>
            <Text style={[styles.logoFallbackText, { color: brand }]}>
              {(session.branding.client_name || "?").slice(0, 1).toUpperCase()}
            </Text>
          </View>
        )}
        <View style={styles.headerText}>
          <Text style={[styles.headerTitle, { color: colors.ink }]} numberOfLines={1}>
            {session.branding.portal_title}
          </Text>
          <Text style={[styles.headerSub, { color: colors.muted }]} numberOfLines={1}>
            {session.user_name || session.branding.agency_name}
          </Text>
        </View>
        <Pressable
          onPress={onSignOut}
          hitSlop={10}
          style={({ pressed }) => pressed && styles.pressed}
          accessibilityRole="button"
          accessibilityLabel={s.list.signOut}
        >
          <Text style={[styles.signOut, { color: brand }]}>{s.list.signOut}</Text>
        </Pressable>
      </View>

      {!loaded ? (
        <View style={styles.center}>
          <ActivityIndicator color={colors.muted} />
        </View>
      ) : (
        <FlatList
          data={items}
          keyExtractor={(item) => item.id}
          contentContainerStyle={items.length ? undefined : styles.emptyContainer}
          contentInsetAdjustmentBehavior="automatic"
          refreshControl={
            <RefreshControl
              refreshing={refreshing}
              tintColor={colors.muted}
              onRefresh={async () => {
                setRefreshing(true);
                await load();
                setRefreshing(false);
              }}
            />
          }
          ItemSeparatorComponent={() => (
            <View style={[styles.separator, { backgroundColor: colors.line }]} />
          )}
          ListEmptyComponent={
            <View style={styles.center}>
              <Text style={[styles.emptyTitle, { color: colors.ink }]}>{s.list.emptyTitle}</Text>
              <Text style={[styles.emptyBody, { color: colors.muted }]}>
                {error || s.list.emptyBody}
              </Text>
            </View>
          }
          renderItem={({ item }) => (
            <Pressable
              onPress={() => onOpen(item)}
              android_ripple={{ color: colors.pressed }}
              style={({ pressed }) => [
                styles.row,
                { backgroundColor: colors.surface },
                pressed && Platform.OS === "ios" && { backgroundColor: colors.pressed },
              ]}
              accessibilityRole="button"
            >
              <View style={[styles.avatar, { backgroundColor: tint(brand, 0.16) }]}>
                <Text style={[styles.avatarText, { color: brand }]}>
                  {(item.contact_name || item.title || "?").slice(0, 1).toUpperCase()}
                </Text>
              </View>
              <View style={styles.rowBody}>
                <View style={styles.rowTop}>
                  <Text style={[styles.rowTitle, { color: colors.ink }]} numberOfLines={1}>
                    {item.contact_name || item.title || s.list.untitled}
                  </Text>
                  <Text style={[styles.rowWhen, { color: colors.subtle }]}>{whenLabel(item.updated_at, s)}</Text>
                </View>
                <Text style={[styles.rowPreview, { color: colors.muted }]} numberOfLines={1}>
                  {item.preview || s.list.noMessages}
                </Text>
                <View style={styles.rowTags}>
                  <Text style={[styles.channel, { color: colors.subtle }]}>
                    {channelLabel(item.channel, s)}
                  </Text>
                  {item.mode === "human" ? (
                    <Text style={[styles.badge, { color: contrastOn(brand), backgroundColor: brand }]}>
                      {s.list.youReply}
                    </Text>
                  ) : null}
                </View>
              </View>
            </Pressable>
          )}
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  header: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    paddingBottom: 12,
    paddingHorizontal: 16,
    borderBottomWidth: StyleSheet.hairlineWidth,
  },
  logo: { width: 36, height: 36, borderRadius: 9 },
  logoFallback: { width: 36, height: 36, borderRadius: 18, alignItems: "center", justifyContent: "center" },
  logoFallbackText: { fontSize: 15, fontWeight: "700" },
  headerText: { flex: 1, minWidth: 0 },
  headerTitle: { fontSize: 17, fontWeight: "700", letterSpacing: -0.2 },
  headerSub: { fontSize: 13, marginTop: 1 },
  signOut: { fontSize: 15 },
  pressed: { opacity: 0.5 },
  emptyContainer: { flexGrow: 1, justifyContent: "center" },
  center: { paddingTop: 40, paddingHorizontal: 40, alignItems: "center" },
  emptyTitle: { fontSize: 17, fontWeight: "600" },
  emptyBody: { marginTop: 8, fontSize: 15, lineHeight: 21, textAlign: "center" },
  separator: { height: StyleSheet.hairlineWidth, marginLeft: 72 },
  row: { flexDirection: "row", gap: 12, paddingHorizontal: 16, paddingVertical: 12 },
  avatar: { width: 44, height: 44, borderRadius: 22, alignItems: "center", justifyContent: "center" },
  avatarText: { fontSize: 17, fontWeight: "600" },
  rowBody: { flex: 1, minWidth: 0 },
  rowTop: { flexDirection: "row", alignItems: "center", gap: 8 },
  rowTitle: { flex: 1, fontSize: 16, fontWeight: "600" },
  rowWhen: { fontSize: 13 },
  rowPreview: { marginTop: 2, fontSize: 15 },
  rowTags: { flexDirection: "row", alignItems: "center", gap: 8, marginTop: 5 },
  channel: { fontSize: 13 },
  badge: {
    fontSize: 11,
    fontWeight: "600",
    paddingHorizontal: 7,
    paddingVertical: 2,
    borderRadius: 20,
    overflow: "hidden",
  },
});
