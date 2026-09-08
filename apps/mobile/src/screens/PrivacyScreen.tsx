import { useEffect, useRef, useState } from "react";
import { ActivityIndicator, Alert, Linking, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import type { Session } from "../api";
import { privacyUrl, supportUrl } from "../privacy";
import { privacyStrings } from "../privacyStrings";
import { contrastOn, readableBrand, useColors, useIsDark } from "../theme";

type Props = {
  session: Session;
  server: string;
  onAccept: () => Promise<void>;
  onDecline: () => Promise<void>;
  onBack?: () => void;
  accepted?: boolean;
};

export function PrivacyScreen({ session, server, onAccept, onDecline, onBack, accepted = false }: Props) {
  const p = privacyStrings(), colors = useColors(), isDark = useIsDark(), insets = useSafeAreaInsets();
  const brand = readableBrand(session.branding.brand_color, isDark);
  const [busy, setBusy] = useState<"accept" | "decline" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const running = useRef(false), mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  const disclosure = session.privacy;
  const destinations = disclosure?.destinations ?? [];
  const policy = privacyUrl(), support = supportUrl();
  let serverHost = server;
  try { serverHost = new URL(server).host; } catch { /* The sign-in screen validates the server address. */ }

  async function run(action: "accept" | "decline") {
    if (running.current || (action === "accept" && (!disclosure?.version || accepted))) return;
    running.current = true; setBusy(action); setError(null);
    try { await (action === "accept" ? onAccept() : onDecline()); }
    catch { if (mounted.current) setError(p.actionFailed); }
    finally { running.current = false; if (mounted.current) setBusy(null); }
  }
  function decline() {
    if (accepted) Alert.alert(p.withdrawTitle, p.withdrawBody, [
      { text: p.cancel, style: "cancel" },
      { text: p.withdraw, style: "destructive", onPress: () => { void run("decline"); } },
    ]);
    else void run("decline");
  }
  async function openLink(url: string) {
    try { await Linking.openURL(url); } catch { Alert.alert(p.linkFailed); }
  }

  return (
    <View style={[styles.screen, { backgroundColor: colors.canvas, paddingTop: insets.top }]}>
      <View style={[styles.header, { borderBottomColor: colors.line }]}>
        {accepted && onBack ? <Pressable onPress={onBack} disabled={!!busy} accessibilityRole="button" accessibilityLabel={p.back} style={styles.back}><Ionicons name="chevron-back" size={24} color={brand} /></Pressable> : null}
        <Text accessibilityRole="header" style={[styles.title, { color: colors.ink }]}>{p.title}</Text>
      </View>
      <ScrollView contentContainerStyle={[styles.content, { paddingBottom: Math.max(insets.bottom, 20) + 20 }]}>
        <Text style={[styles.intro, { color: colors.ink }]}>{accepted ? p.reviewIntro : p.intro}</Text>
        <View style={[styles.card, { backgroundColor: colors.surface, borderColor: colors.line }]}>
          <Text style={{ color: colors.muted, fontSize: 13 }}>{p.account}</Text>
          <Text style={{ color: colors.ink, fontSize: 17, fontWeight: "700" }}>{session.branding.client_name}</Text>
          <Text selectable style={{ color: colors.muted, fontSize: 14 }}>{serverHost}</Text>
        </View>
        {[[p.storedTitle, p.stored], [p.aiTitle, p.ai], [p.notificationsTitle, p.notifications]].map(([title, body]) => (
          <View key={title} style={styles.section}>
            <Text accessibilityRole="header" style={[styles.heading, { color: colors.ink }]}>{title}</Text>
            <Text style={[styles.body, { color: colors.muted }]}>{body}</Text>
          </View>
        ))}
        <View style={styles.section}>
          <Text accessibilityRole="header" style={[styles.heading, { color: colors.ink }]}>{p.destinationsTitle}</Text>
          {destinations.length ? destinations.map((destination, index) => (
            <View key={`${destination.kind}:${destination.host}:${index}`} style={[styles.card, { backgroundColor: colors.surface, borderColor: colors.line }]}>
              <Text style={{ color: colors.muted, fontSize: 13 }}>{destination.kind === "ai" ? p.aiKind : destination.kind === "notification" ? p.notificationKind : p.integrationKind}</Text>
              <Text style={{ color: colors.ink, fontSize: 16, fontWeight: "600" }}>{destination.name}</Text>
              {!!destination.host && <Text selectable style={[styles.body, { color: colors.muted }]}>{destination.host}</Text>}
              {destination.capabilities.length ? <Text style={[styles.body, { color: colors.muted }]}>{destination.capabilities.map((capability) => Object.hasOwn(p.capabilities, capability) ? p.capabilities[capability as keyof typeof p.capabilities] : capability.replaceAll("_", " ")).join(" · ")}</Text> : null}
            </View>
          )) : disclosure ? <Text style={[styles.body, { color: colors.muted }]}>{p.noDestinations}</Text> : null}
        </View>
        <View style={styles.links}>
          {policy ? <Pressable accessibilityRole="link" onPress={() => { void openLink(policy); }} style={styles.link}><Text style={{ color: brand, fontSize: 16 }}>{p.policy}</Text></Pressable> : null}
          {support ? <Pressable accessibilityRole="link" onPress={() => { void openLink(support); }} style={styles.link}><Text style={{ color: brand, fontSize: 16 }}>{p.support}</Text></Pressable> : null}
        </View>
        {!accepted ? <Text style={[styles.body, { color: colors.ink }]}>{p.consent}</Text> : null}
        {!disclosure?.version && !accepted ? <Text accessibilityRole="alert" style={[styles.body, { color: colors.danger }]}>{p.unavailable}</Text> : null}
        {error ? <Text accessibilityRole="alert" accessibilityLiveRegion="polite" style={[styles.body, { color: colors.danger }]}>{error}</Text> : null}
        {!accepted ? <Pressable testID="privacy-accept" onPress={() => { void run("accept"); }} disabled={!!busy || !disclosure?.version} accessibilityRole="button" accessibilityState={{ disabled: !!busy || !disclosure?.version, busy: busy === "accept" }} style={[styles.button, { backgroundColor: brand, opacity: busy || !disclosure?.version ? 0.5 : 1 }]}>{busy === "accept" ? <ActivityIndicator color={contrastOn(brand)} /> : <Text style={[styles.buttonText, { color: contrastOn(brand) }]}>{p.accept}</Text>}</Pressable> : null}
        <Pressable testID="privacy-decline" onPress={decline} disabled={!!busy} accessibilityRole="button" accessibilityState={{ disabled: !!busy, busy: busy === "decline" }} style={[styles.button, { borderColor: colors.line, borderWidth: 1 }]}>{busy === "decline" ? <ActivityIndicator color={colors.danger} /> : <Text style={[styles.buttonText, { color: colors.danger }]}>{accepted ? p.withdraw : p.decline}</Text>}</Pressable>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1 }, header: { flexDirection: "row", alignItems: "center", minHeight: 58, paddingHorizontal: 16, borderBottomWidth: StyleSheet.hairlineWidth },
  back: { minWidth: 44, minHeight: 44, alignItems: "center", justifyContent: "center", marginLeft: -10 }, title: { flex: 1, fontSize: 21, fontWeight: "700" },
  content: { padding: 20, gap: 20, maxWidth: 760, width: "100%", alignSelf: "center" }, intro: { fontSize: 20, lineHeight: 28, fontWeight: "600" },
  section: { gap: 10 }, heading: { fontSize: 17, fontWeight: "700" }, body: { fontSize: 15, lineHeight: 23 }, card: { borderWidth: StyleSheet.hairlineWidth, borderRadius: 12, padding: 14, gap: 6 },
  links: { flexDirection: "row", flexWrap: "wrap", gap: 20 }, link: { minHeight: 44, justifyContent: "center" }, button: { minHeight: 50, borderRadius: 12, padding: 14, alignItems: "center", justifyContent: "center" }, buttonText: { fontSize: 16, fontWeight: "600", textAlign: "center" },
});
