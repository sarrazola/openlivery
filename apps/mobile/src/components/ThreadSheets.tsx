import { useEffect, useState, type ReactNode } from "react";
import { ActivityIndicator, KeyboardAvoidingView, Modal, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { listTemplates, type Session, type Template, type TemplateSend } from "../api";
import { chatStrings } from "../chatStrings";
import { contrastOn, tint, useColors } from "../theme";

export function ThreadSheet({ visible, title, onClose, children }: { visible: boolean; title: string; onClose: () => void; children: ReactNode }) {
  const colors = useColors();
  const c = chatStrings();
  const insets = useSafeAreaInsets();
  return <Modal transparent visible={visible} animationType="slide" onRequestClose={onClose}>
    <KeyboardAvoidingView style={styles.scrim} behavior={Platform.OS === "ios" ? "padding" : undefined}>
      <Pressable style={StyleSheet.absoluteFill} onPress={onClose} accessibilityRole="button" accessibilityLabel={c.close} />
      <View style={[styles.sheet, { backgroundColor: colors.surface, paddingBottom: Math.max(insets.bottom, 16), maxHeight: "90%" }]} accessibilityViewIsModal>
        <View style={styles.handleRow}><View style={[styles.handle, { backgroundColor: colors.line }]} /></View>
        <View style={[styles.header, { borderBottomColor: colors.line }]}>
          <Text accessibilityRole="header" style={[styles.title, { color: colors.ink }]}>{title}</Text>
          <Pressable onPress={onClose} hitSlop={10} style={styles.close} accessibilityRole="button" accessibilityLabel={c.close}><Ionicons name="close" size={24} color={colors.muted} /></Pressable>
        </View>
        <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={styles.content}>{children}</ScrollView>
      </View>
    </KeyboardAvoidingView>
  </Modal>;
}

export function ThreadAction({ label, subtitle, icon, onPress, brand, selected, disabled, filled }: { label: string; subtitle?: string; icon?: keyof typeof Ionicons.glyphMap; onPress: () => void; brand: string; selected?: boolean; disabled?: boolean; filled?: boolean }) {
  const colors = useColors();
  const color = filled ? contrastOn(brand) : colors.ink;
  return <Pressable onPress={onPress} disabled={disabled} accessibilityRole="button" accessibilityState={{ disabled: Boolean(disabled), selected: Boolean(selected) }} style={({ pressed }) => [styles.action, { backgroundColor: filled ? brand : selected ? tint(brand) : colors.raised, borderColor: selected ? brand : colors.line }, (pressed || disabled) && { opacity: .55 }]}>
    {icon ? <Ionicons name={icon} size={20} color={filled ? color : brand} /> : null}
    <View style={{ flex: 1 }}><Text style={[styles.actionLabel, { color }]}>{label}</Text>{subtitle ? <Text style={{ fontSize: 12, marginTop: 3, color: filled ? color : colors.muted }}>{subtitle}</Text> : null}</View>
    {selected ? <Ionicons name="checkmark" size={20} color={brand} /> : null}
  </Pressable>;
}

export function TemplatePicker({ externalError, visible, server, session, brand, onClose, onSend }: { externalError?: string | null; visible: boolean; server: string; session: Session; brand: string; onClose: () => void; onSend: (payload: TemplateSend) => Promise<boolean> }) {
  const c = chatStrings();
  const colors = useColors();
  const [items, setItems] = useState<Template[]>([]);
  const [chosen, setChosen] = useState<Template | null>(null);
  const [values, setValues] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    if (!visible) return;
    let cancelled = false;
    setLoading(true); setError(null); setChosen(null); setValues([]);
    listTemplates(server, session).then((data) => { if (!cancelled) setItems(data.filter((item) => item.status === "APPROVED")); }).catch((err) => { if (!cancelled) setError(err instanceof Error ? err.message : c.loadFailed); }).finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [visible, server, session, attempt]);
  return <ThreadSheet visible={visible} title={c.templates} onClose={() => { if (!busy) onClose(); }}>
    {loading ? <ActivityIndicator color={brand} style={{ padding: 24 }} /> : items.length ? items.map((item) => <ThreadAction key={`${item.name}:${item.language}`} brand={brand} label={item.name} subtitle={item.language} selected={chosen === item} disabled={busy} onPress={() => { setChosen(item); setValues(Array.from({ length: item.variables }, () => "")); }} />) : !error ? <Text style={[styles.help, { color: colors.muted }]}>{c.noTemplates}</Text> : null}
    {chosen ? <View style={{ gap: 12, marginTop: 14 }}>
      {values.map((value, index) => <View key={index}><Text style={{ color: colors.muted, marginBottom: 5 }}>{c.templateValue} {index + 1}</Text><TextInput accessibilityLabel={`${c.templateValue} ${index + 1}`} editable={!busy} value={value} onChangeText={(next) => setValues((prev) => prev.map((old, i) => i === index ? next : old))} style={[styles.input, { color: colors.ink, borderColor: colors.line, backgroundColor: colors.canvas }]} /></View>)}
      <View style={[styles.preview, { backgroundColor: tint(brand, .08) }]}><Text style={{ color: brand, fontSize: 12, fontWeight: "600", marginBottom: 8 }}>{c.preview}</Text><Text style={{ color: colors.ink, lineHeight: 22 }}>{chosen.body.replace(/\{\{(\d+)\}\}/g, (whole, n: string) => values[Number(n) - 1] || whole)}</Text>{chosen.footer ? <Text style={{ color: colors.muted, fontSize: 12, marginTop: 10 }}>{chosen.footer}</Text> : null}</View>
      <ThreadAction label={busy ? c.pending : c.sendTemplate} icon="send-outline" brand={brand} filled disabled={busy || values.some((value) => !value.trim())} onPress={async () => { setBusy(true); setError(null); try { if (await onSend({ name: chosen.name, language: chosen.language, variables: values.map((value) => value.trim()) })) onClose(); else setError(c.updateFailed); } catch (err) { setError(err instanceof Error ? err.message : c.updateFailed); } finally { setBusy(false); } }} />
    </View> : null}
    {error || externalError ? <View><Text accessibilityRole="alert" style={{ color: colors.danger, paddingVertical: 12 }}>{externalError || error}</Text>{!chosen ? <ThreadAction label={c.retry} brand={brand} onPress={() => setAttempt((count) => count + 1)} /> : null}</View> : null}
  </ThreadSheet>;
}
const styles = StyleSheet.create({
  scrim: { flex: 1, justifyContent: "flex-end", backgroundColor: "rgba(0,0,0,.45)" }, sheet: { borderTopLeftRadius: 24, borderTopRightRadius: 24, overflow: "hidden" }, handleRow: { alignItems: "center", paddingTop: 9 }, handle: { height: 4, width: 36, borderRadius: 3 },
  header: { flexDirection: "row", alignItems: "center", paddingHorizontal: 20, paddingVertical: 14, gap: 12, borderBottomWidth: StyleSheet.hairlineWidth }, title: { fontSize: 19, fontWeight: "700", flex: 1 }, close: { padding: 4 }, content: { padding: 18, gap: 8 },
  action: { flexDirection: "row", gap: 12, alignItems: "center", minHeight: 50, padding: 13, borderRadius: 12, borderWidth: StyleSheet.hairlineWidth }, actionLabel: { fontSize: 15, fontWeight: "600" }, help: { lineHeight: 22, fontSize: 14, padding: 8 }, input: { padding: 13, fontSize: 16, borderWidth: 1, borderRadius: 10 }, preview: { padding: 16, borderRadius: 12 },
});
