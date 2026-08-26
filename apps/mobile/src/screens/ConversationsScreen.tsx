import { useCallback, useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  FlatList,
  Image,
  RefreshControl,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from "react-native";
import { assetUrl, listConversations, type Conversation, type Session } from "../api";
import { contrastOn, palette, tint } from "../theme";

const CHANNEL_LABELS: Record<string, string> = {
  whatsapp: "WhatsApp",
  whatsapp_cloud: "WhatsApp",
  widget: "Web chat",
  playground: "Playground",
};

function whenLabel(iso: string): string {
  const date = new Date(iso);
  const now = new Date();
  const sameDay = date.toDateString() === now.toDateString();
  if (sameDay) return date.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
  const yesterday = new Date(now);
  yesterday.setDate(now.getDate() - 1);
  if (date.toDateString() === yesterday.toDateString()) return "Yesterday";
  return date.toLocaleDateString(undefined, { day: "numeric", month: "short" });
}

/**
 * The list of conversations for this business. Polls while it is on screen,
 * which is the honest option until the server can push: the interval is slower
 * than the web inbox because a phone pays for it in battery.
 */
export function ConversationsScreen({
  server,
  session,
  onOpen,
  onSignOut,
  autoOpenFirst = false,
}: {
  server: string;
  session: Session;
  onOpen: (conversation: Conversation) => void;
  onSignOut: () => void;
  autoOpenFirst?: boolean;
}) {
  const [items, setItems] = useState<Conversation[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const mounted = useRef(true);
  const autoOpened = useRef(false);

  const brand = session.branding.brand_color;
  const logo = assetUrl(server, session.branding.client_logo_url || session.branding.agency_logo_url);

  const load = useCallback(async () => {
    try {
      const rows = await listConversations(server, session);
      if (mounted.current) {
        setItems(rows);
        setError(null);
      }
    } catch (err) {
      if (mounted.current) setError(err instanceof Error ? err.message : "Could not load conversations");
    } finally {
      if (mounted.current) setLoaded(true);
    }
  }, [server, session]);

  useEffect(() => {
    if (!autoOpenFirst || autoOpened.current || !items.length) return;
    autoOpened.current = true;
    onOpen(items[0]);
  }, [autoOpenFirst, items, onOpen]);

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
    <View style={styles.flex}>
      <View style={[styles.header, { backgroundColor: brand }]}>
        <View style={styles.headerRow}>
          {logo ? <Image source={{ uri: logo }} style={styles.logo} resizeMode="contain" /> : null}
          <View style={styles.headerText}>
            <Text style={[styles.headerTitle, { color: contrastOn(brand) }]} numberOfLines={1}>
              {session.branding.portal_title}
            </Text>
            <Text style={[styles.headerSub, { color: contrastOn(brand) }]} numberOfLines={1}>
              {session.branding.agency_name}
            </Text>
          </View>
          <TouchableOpacity onPress={onSignOut} accessibilityRole="button" accessibilityLabel="Sign out">
            <Text style={[styles.signOut, { color: contrastOn(brand) }]}>Sign out</Text>
          </TouchableOpacity>
        </View>
      </View>

      {!loaded ? (
        <View style={styles.center}>
          <ActivityIndicator color={brand} />
        </View>
      ) : (
        <FlatList
          data={items}
          keyExtractor={(item) => item.id}
          refreshControl={
            <RefreshControl
              refreshing={refreshing}
              tintColor={brand}
              onRefresh={async () => {
                setRefreshing(true);
                await load();
                setRefreshing(false);
              }}
            />
          }
          ListEmptyComponent={
            <View style={styles.center}>
              <Text style={styles.emptyTitle}>No conversations yet</Text>
              <Text style={styles.emptyBody}>
                {error || "When someone writes to your assistant, the conversation shows up here."}
              </Text>
            </View>
          }
          renderItem={({ item }) => (
            <TouchableOpacity style={styles.row} onPress={() => onOpen(item)} accessibilityRole="button">
              <View style={[styles.avatar, { backgroundColor: tint(brand, 0.14) }]}>
                <Text style={[styles.avatarText, { color: brand }]}>
                  {(item.contact_name || item.title || "?").slice(0, 1).toUpperCase()}
                </Text>
              </View>
              <View style={styles.rowBody}>
                <View style={styles.rowTop}>
                  <Text style={styles.rowTitle} numberOfLines={1}>
                    {item.contact_name || item.title || "Conversation"}
                  </Text>
                  <Text style={styles.rowWhen}>{whenLabel(item.updated_at)}</Text>
                </View>
                <Text style={styles.rowPreview} numberOfLines={1}>
                  {item.preview || "No messages yet"}
                </Text>
                <View style={styles.rowTags}>
                  <Text style={styles.channel}>{CHANNEL_LABELS[item.channel] || item.channel}</Text>
                  {item.mode === "human" ? (
                    <Text style={[styles.badge, { color: brand, backgroundColor: tint(brand, 0.14) }]}>You reply</Text>
                  ) : null}
                </View>
              </View>
            </TouchableOpacity>
          )}
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1, backgroundColor: palette.canvas },
  header: { paddingTop: 58, paddingBottom: 16, paddingHorizontal: 18 },
  headerRow: { flexDirection: "row", alignItems: "center", gap: 12 },
  logo: { width: 38, height: 38, borderRadius: 9, backgroundColor: "#fff" },
  headerText: { flex: 1 },
  headerTitle: { fontSize: 19, fontWeight: "700" },
  headerSub: { fontSize: 13, opacity: 0.8, marginTop: 2 },
  signOut: { fontSize: 13, fontWeight: "600", opacity: 0.9 },
  center: { paddingTop: 80, paddingHorizontal: 40, alignItems: "center" },
  emptyTitle: { fontSize: 16, fontWeight: "600", color: palette.ink },
  emptyBody: { marginTop: 8, fontSize: 14, lineHeight: 20, color: palette.muted, textAlign: "center" },
  row: {
    flexDirection: "row",
    gap: 12,
    paddingHorizontal: 16,
    paddingVertical: 14,
    backgroundColor: palette.surface,
    borderBottomWidth: 1,
    borderBottomColor: palette.line,
  },
  avatar: { width: 44, height: 44, borderRadius: 22, alignItems: "center", justifyContent: "center" },
  avatarText: { fontSize: 17, fontWeight: "700" },
  rowBody: { flex: 1, minWidth: 0 },
  rowTop: { flexDirection: "row", alignItems: "center", gap: 8 },
  rowTitle: { flex: 1, fontSize: 15, fontWeight: "600", color: palette.ink },
  rowWhen: { fontSize: 12, color: palette.subtle },
  rowPreview: { marginTop: 3, fontSize: 14, color: palette.muted },
  rowTags: { flexDirection: "row", alignItems: "center", gap: 8, marginTop: 6 },
  channel: { fontSize: 12, color: palette.subtle },
  badge: { fontSize: 12, fontWeight: "600", paddingHorizontal: 8, paddingVertical: 2, borderRadius: 20, overflow: "hidden" },
});
