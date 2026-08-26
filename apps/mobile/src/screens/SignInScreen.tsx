import { useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from "react-native";
import { ApiError, normalizeServerUrl, signIn, type Session } from "../api";
import { BRAND_COLOR, DEFAULT_SERVER, HOSTED, hostedServerFor } from "../brand";
import { contrastOn, useColors } from "../theme";

/**
 * Signing in.
 *
 * The app is not tied to one server, so it needs to be told which one: the
 * address of the instance the agency runs, plus the portal credentials the
 * agency handed to this business. The portal is resolved from the credentials,
 * so nobody has to know what a slug is.
 *
 * A build compiled with a hosted preset (see src/brand.ts) offers that service
 * as a choice, where naming a workspace is enough and the address is derived.
 * Without one - which is every build from this repository - it simply asks for
 * the address.
 */
// Filled from EXPO_PUBLIC_DEV_* when present, so a local run does not mean
// retyping a server and credentials on every reload. These are inlined at build
// time, so a release build must not define them.
const DEV_SERVER = process.env.EXPO_PUBLIC_DEV_SERVER || "";
const DEV_EMAIL = process.env.EXPO_PUBLIC_DEV_EMAIL || "";
const DEV_PASSWORD = process.env.EXPO_PUBLIC_DEV_PASSWORD || "";

export function SignInScreen({ onSignedIn }: { onSignedIn: (server: string, session: Session) => void }) {
  // Default to the hosted service when this build has one: it is what most of
  // its users want, and the others are one tap away.
  const [useHosted, setUseHosted] = useState(Boolean(HOSTED) && !DEV_SERVER);
  const [workspace, setWorkspace] = useState("");
  const [server, setServer] = useState(DEV_SERVER || DEFAULT_SERVER);
  const [email, setEmail] = useState(DEV_EMAIL);
  const [password, setPassword] = useState(DEV_PASSWORD);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const colors = useColors();

  const target = useHosted ? workspace : server;
  const canSubmit = target.trim().length > 0 && email.trim().length > 0 && password.length > 0 && !busy;
  const autoAttempted = useRef(false);

  // With all three dev variables set, go straight in. Only ever true on a local
  // run, since a release build has none of them defined.
  useEffect(() => {
    if (autoAttempted.current || !DEV_SERVER || !DEV_EMAIL || !DEV_PASSWORD) return;
    autoAttempted.current = true;
    submit();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function submit() {
    if (!canSubmit) return;
    setBusy(true);
    setError(null);
    const base = useHosted ? hostedServerFor(workspace) : normalizeServerUrl(server);
    try {
      const session = await signIn(base, email.trim(), password);
      onSignedIn(base, session);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not sign in");
      setBusy(false);
    }
  }

  return (
    <KeyboardAvoidingView style={[styles.flex, { backgroundColor: colors.canvas }]} behavior={Platform.OS === "ios" ? "padding" : undefined}>
      <ScrollView contentContainerStyle={styles.scroll} keyboardShouldPersistTaps="handled">
        <View style={styles.header}>
          <Text style={[styles.title, { color: colors.ink }]}>Your inbox</Text>
          <Text style={[styles.subtitle, { color: colors.muted }]}>Sign in with the details your agency gave you.</Text>
        </View>

        <View style={[styles.form, { backgroundColor: colors.surface, borderColor: colors.line }]}>
          {HOSTED ? (
            <View style={[styles.switcher, { backgroundColor: colors.canvas }]}>
              {[
                { active: true, label: HOSTED.label },
                { active: false, label: HOSTED.otherLabel },
              ].map((option) => {
                const selected = useHosted === option.active;
                return (
                  <TouchableOpacity
                    key={option.label}
                    style={[styles.switcherOption, selected && [styles.switcherOptionOn, { backgroundColor: colors.surface }]]}
                    onPress={() => setUseHosted(option.active)}
                    accessibilityRole="button"
                    accessibilityState={{ selected }}
                  >
                    <Text style={[styles.switcherText, { color: colors.muted }, selected && { color: colors.ink }]} numberOfLines={1}>
                      {option.label}
                    </Text>
                  </TouchableOpacity>
                );
              })}
            </View>
          ) : null}

          {useHosted && HOSTED ? (
            // A View rather than a fragment: React treats a fragment's children
            // here as an unkeyed list and warns about it.
            <View>
              <Text style={[styles.label, { color: colors.ink }]}>{HOSTED.workspaceLabel}</Text>
              <TextInput
                style={[styles.input, { borderColor: colors.line, color: colors.ink, backgroundColor: colors.surface }]}
                value={workspace}
                onChangeText={setWorkspace}
                placeholder={HOSTED.workspacePlaceholder}
                placeholderTextColor={colors.subtle}
                autoCapitalize="none"
                autoCorrect={false}
                returnKeyType="next"
              />
              {workspace.trim() ? <Text style={[styles.hint, { color: colors.subtle }]}>{hostedServerFor(workspace)}</Text> : null}
            </View>
          ) : (
            <View>
              <Text style={[styles.label, { color: colors.ink }]}>Server address</Text>
              <TextInput
                style={[styles.input, { borderColor: colors.line, color: colors.ink, backgroundColor: colors.surface }]}
                value={server}
                onChangeText={setServer}
                placeholder="chat.myagency.com"
                placeholderTextColor={colors.subtle}
                autoCapitalize="none"
                autoCorrect={false}
                keyboardType="url"
                returnKeyType="next"
              />
              <Text style={[styles.hint, { color: colors.subtle }]}>The address of the instance your agency runs.</Text>
            </View>
          )}

          <Text style={[styles.label, { color: colors.ink }]}>E-mail</Text>
          <TextInput
            style={[styles.input, { borderColor: colors.line, color: colors.ink, backgroundColor: colors.surface }]}
            value={email}
            onChangeText={setEmail}
            placeholder="you@business.com"
            placeholderTextColor={colors.subtle}
            autoCapitalize="none"
            autoCorrect={false}
            keyboardType="email-address"
            textContentType="username"
            returnKeyType="next"
          />

          <Text style={[styles.label, { color: colors.ink }]}>Password</Text>
          <TextInput
            style={[styles.input, { borderColor: colors.line, color: colors.ink, backgroundColor: colors.surface }]}
            value={password}
            onChangeText={setPassword}
            placeholder="••••••••"
            placeholderTextColor={colors.subtle}
            secureTextEntry
            textContentType="password"
            returnKeyType="go"
            onSubmitEditing={submit}
          />

          {error ? <Text style={[styles.error, { color: colors.danger }]}>{error}</Text> : null}

          <TouchableOpacity
            style={[styles.button, { backgroundColor: BRAND_COLOR }, !canSubmit && styles.buttonDisabled]}
            onPress={submit}
            disabled={!canSubmit}
            accessibilityRole="button"
          >
            {busy ? (
              <ActivityIndicator color={contrastOn(BRAND_COLOR)} />
            ) : (
              <Text style={[styles.buttonText, { color: contrastOn(BRAND_COLOR) }]}>Sign in</Text>
            )}
          </TouchableOpacity>
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  scroll: { flexGrow: 1, justifyContent: "center", padding: 24 },
  header: { marginBottom: 28 },
  title: { fontSize: 30, fontWeight: "700", letterSpacing: -0.5 },
  subtitle: { marginTop: 8, fontSize: 15, lineHeight: 21 },
  form: { borderRadius: 16, padding: 20, borderWidth: StyleSheet.hairlineWidth },
  switcher: { flexDirection: "row", borderRadius: 9, padding: 3, gap: 3 },
  switcherOption: { flex: 1, paddingVertical: 8, borderRadius: 7, alignItems: "center" },
  switcherOptionOn: Platform.select({
    ios: { shadowColor: "#000", shadowOpacity: 0.12, shadowRadius: 3, shadowOffset: { width: 0, height: 1 } },
    android: { elevation: 1 },
    default: {},
  }),
  switcherText: { fontSize: 13, fontWeight: "600" },

  label: { fontSize: 13, fontWeight: "600", marginBottom: 6, marginTop: 14 },
  input: {
    height: 48,
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: 10,
    paddingHorizontal: 14,
    fontSize: 16,
  },
  hint: { marginTop: 6, fontSize: 12, lineHeight: 17 },
  error: { marginTop: 16, fontSize: 14, lineHeight: 19 },
  button: { marginTop: 24, height: 50, borderRadius: 10, alignItems: "center", justifyContent: "center" },
  buttonDisabled: { opacity: 0.45 },
  buttonText: { fontSize: 16, fontWeight: "600" },
});
