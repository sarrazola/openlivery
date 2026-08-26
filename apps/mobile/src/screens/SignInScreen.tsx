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
import { DEFAULT_BRAND, contrastOn, palette } from "../theme";

/**
 * Three fields, because the app is not tied to one server: the address of the
 * instance the agency runs, and the portal credentials the agency handed to
 * this business. The portal is resolved from the credentials, so nobody has to
 * know what a slug is.
 */
// Filled from EXPO_PUBLIC_DEV_* when present, so a local run does not mean
// retyping a server and credentials on every reload. These are inlined at build
// time, so a release build must not define them.
const DEV_SERVER = process.env.EXPO_PUBLIC_DEV_SERVER || "";
const DEV_EMAIL = process.env.EXPO_PUBLIC_DEV_EMAIL || "";
const DEV_PASSWORD = process.env.EXPO_PUBLIC_DEV_PASSWORD || "";

export function SignInScreen({ onSignedIn }: { onSignedIn: (server: string, session: Session) => void }) {
  const [server, setServer] = useState(DEV_SERVER);
  const [email, setEmail] = useState(DEV_EMAIL);
  const [password, setPassword] = useState(DEV_PASSWORD);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canSubmit = server.trim().length > 0 && email.trim().length > 0 && password.length > 0 && !busy;
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
    const base = normalizeServerUrl(server);
    try {
      const session = await signIn(base, email.trim(), password);
      onSignedIn(base, session);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not sign in");
      setBusy(false);
    }
  }

  return (
    <KeyboardAvoidingView style={styles.flex} behavior={Platform.OS === "ios" ? "padding" : undefined}>
      <ScrollView contentContainerStyle={styles.scroll} keyboardShouldPersistTaps="handled">
        <View style={styles.header}>
          <Text style={styles.title}>Your inbox</Text>
          <Text style={styles.subtitle}>Sign in with the details your agency gave you.</Text>
        </View>

        <View style={styles.form}>
          <Text style={styles.label}>Server address</Text>
          <TextInput
            style={styles.input}
            value={server}
            onChangeText={setServer}
            placeholder="chat.myagency.com"
            placeholderTextColor={palette.subtle}
            autoCapitalize="none"
            autoCorrect={false}
            keyboardType="url"
            returnKeyType="next"
          />
          <Text style={styles.hint}>The address of your agency's OpenLivery instance.</Text>

          <Text style={styles.label}>E-mail</Text>
          <TextInput
            style={styles.input}
            value={email}
            onChangeText={setEmail}
            placeholder="you@business.com"
            placeholderTextColor={palette.subtle}
            autoCapitalize="none"
            autoCorrect={false}
            keyboardType="email-address"
            returnKeyType="next"
          />

          <Text style={styles.label}>Password</Text>
          <TextInput
            style={styles.input}
            value={password}
            onChangeText={setPassword}
            placeholder="••••••••"
            placeholderTextColor={palette.subtle}
            secureTextEntry
            returnKeyType="go"
            onSubmitEditing={submit}
          />

          {error ? <Text style={styles.error}>{error}</Text> : null}

          <TouchableOpacity
            style={[styles.button, { backgroundColor: DEFAULT_BRAND }, !canSubmit && styles.buttonDisabled]}
            onPress={submit}
            disabled={!canSubmit}
            accessibilityRole="button"
          >
            {busy ? (
              <ActivityIndicator color={contrastOn(DEFAULT_BRAND)} />
            ) : (
              <Text style={[styles.buttonText, { color: contrastOn(DEFAULT_BRAND) }]}>Sign in</Text>
            )}
          </TouchableOpacity>
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1, backgroundColor: palette.canvas },
  scroll: { flexGrow: 1, justifyContent: "center", padding: 24 },
  header: { marginBottom: 28 },
  title: { fontSize: 30, fontWeight: "700", color: palette.ink, letterSpacing: -0.5 },
  subtitle: { marginTop: 8, fontSize: 15, lineHeight: 21, color: palette.muted },
  form: { backgroundColor: palette.surface, borderRadius: 16, padding: 20, borderWidth: 1, borderColor: palette.line },
  label: { fontSize: 13, fontWeight: "600", color: palette.ink, marginBottom: 6, marginTop: 14 },
  input: {
    height: 48,
    borderWidth: 1,
    borderColor: palette.line,
    borderRadius: 10,
    paddingHorizontal: 14,
    fontSize: 15,
    color: palette.ink,
    backgroundColor: palette.surface,
  },
  hint: { marginTop: 6, fontSize: 12, lineHeight: 17, color: palette.subtle },
  error: { marginTop: 16, fontSize: 13, lineHeight: 18, color: palette.danger },
  button: { marginTop: 24, height: 50, borderRadius: 10, alignItems: "center", justifyContent: "center" },
  buttonDisabled: { opacity: 0.45 },
  buttonText: { fontSize: 16, fontWeight: "600" },
});
