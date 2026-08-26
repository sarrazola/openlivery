/**
 * Writing back: text, a photo, a file, or a voice note.
 *
 * Laid out the way WhatsApp lays it out, because the people using this already
 * answer their customers there and should not have to learn a second shape:
 * attach on the left, the field, then the camera, then a microphone that turns
 * into a send button the moment there is something to send.
 *
 * Recording replaces the whole row - a level meter, the elapsed time, and
 * delete / pause / send - because a half-recorded voice note that still looks
 * like a text field is the fastest way to send silence.
 */

import { useEffect, useRef, useState } from "react";
import {
  ActionSheetIOS,
  ActivityIndicator,
  Alert,
  Animated,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import * as ImagePicker from "expo-image-picker";
import {
  AudioModule,
  RecordingPresets,
  setAudioModeAsync,
  useAudioRecorder,
  useAudioRecorderState,
} from "expo-audio";
import { useStrings } from "../i18n";
import { contrastOn, tint, useColors } from "../theme";

export type OutgoingFile = { uri: string; name: string; type: string };

type Props = {
  brand: string;
  busy: boolean;
  onSendText: (text: string) => void;
  onSendFile: (file: OutgoingFile) => void;
};

function extensionFor(uri: string, fallback: string): string {
  const match = /\.([a-z0-9]{2,5})(?:\?|$)/i.exec(uri);
  return match ? match[1].toLowerCase() : fallback;
}

const IMAGE_MIME: Record<string, string> = {
  jpg: "image/jpeg",
  jpeg: "image/jpeg",
  png: "image/png",
  webp: "image/webp",
  heic: "image/heic",
  gif: "image/gif",
};

/** How many bars the meter draws. Enough to read as sound, few enough to be cheap. */
const BARS = 26;
const METER_INTERVAL_MS = 90;

function formatDuration(millis: number | undefined): string {
  const total = Math.floor((millis || 0) / 1000);
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}

/** Turn the recorder's decibel reading into a 0..1 height. */
function levelFrom(metering: number | undefined): number {
  if (metering === undefined || !Number.isFinite(metering)) return 0.08;
  // Metering is dBFS: 0 is as loud as it gets, -60 is effectively silence.
  const normalised = (Math.max(-60, Math.min(0, metering)) + 60) / 60;
  return Math.max(0.08, normalised ** 1.6);
}

function Meter({ levels, color }: { levels: number[]; color: string }) {
  return (
    <View style={styles.meter}>
      {levels.map((level, index) => (
        <View
          key={index}
          style={[styles.meterBar, { height: 4 + level * 22, backgroundColor: color }]}
        />
      ))}
    </View>
  );
}

export function Composer({ brand, busy, onSendText, onSendFile }: Props) {
  const colors = useColors();
  const s = useStrings();
  const [draft, setDraft] = useState("");
  const [sheetOpen, setSheetOpen] = useState(false);
  const recorder = useAudioRecorder({ ...RecordingPresets.HIGH_QUALITY, isMeteringEnabled: true });
  const recorderState = useAudioRecorderState(recorder, METER_INTERVAL_MS);
  const [preparing, setPreparing] = useState(false);
  const [paused, setPaused] = useState(false);
  const [levels, setLevels] = useState<number[]>(() => new Array(BARS).fill(0.08));
  const blink = useRef(new Animated.Value(1)).current;

  const recording = recorderState.isRecording || paused;
  const canSend = draft.trim().length > 0 && !busy;

  // Keep the newest reading somewhere the timer below can see it without
  // becoming a dependency of it.
  const metering = useRef<number | undefined>(undefined);
  metering.current = recorderState.metering;

  // Slide a reading in from the right on a timer, so the meter reads
  // left-to-right like a tape going past. Driven by the clock rather than by
  // the reading changing: silence reports the same number every time, and a
  // meter that freezes while someone is still recording looks like a hang.
  useEffect(() => {
    if (!recorderState.isRecording) return;
    const tape = setInterval(() => {
      setLevels((previous) => [...previous.slice(1), levelFrom(metering.current)]);
    }, METER_INTERVAL_MS);
    return () => clearInterval(tape);
  }, [recorderState.isRecording]);

  useEffect(() => {
    if (!recording) return;
    const pulse = Animated.loop(
      Animated.sequence([
        Animated.timing(blink, { toValue: 0.25, duration: 600, useNativeDriver: true }),
        Animated.timing(blink, { toValue: 1, duration: 600, useNativeDriver: true }),
      ]),
    );
    pulse.start();
    return () => pulse.stop();
  }, [recording, blink]);

  // Deliberately no cleanup that touches the recorder.
  //
  // useAudioRecorder releases the native recorder in its own unmount cleanup,
  // and that cleanup is registered before anything this component adds - so a
  // cleanup here reading `recorder.isRecording` reaches an object that has
  // just been freed and throws out of an unmount. That is what took the screen
  // down on the way back from a conversation and on signing out. Releasing the
  // recorder stops it, so there was nothing to do here anyway.

  // Anything that resumes after an await has to check it still has a component
  // to return to, for the same reason.
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  function send() {
    if (!canSend) return;
    const text = draft.trim();
    setDraft("");
    onSendText(text);
  }

  async function pick(from: "library" | "camera") {
    setSheetOpen(false);
    const permission =
      from === "camera"
        ? await ImagePicker.requestCameraPermissionsAsync()
        : await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!permission.granted) {
      Alert.alert(
        from === "camera" ? s.composer.cameraDeniedTitle : s.composer.photosDeniedTitle,
        s.composer.mediaDeniedBody,
      );
      return;
    }
    const options: ImagePicker.ImagePickerOptions = {
      mediaTypes: ["images", "videos"],
      quality: 0.8,
      allowsMultipleSelection: false,
    };
    const result =
      from === "camera"
        ? await ImagePicker.launchCameraAsync(options)
        : await ImagePicker.launchImageLibraryAsync(options);
    if (result.canceled || !result.assets?.length) return;
    const asset = result.assets[0];
    const extension = extensionFor(asset.uri, asset.type === "video" ? "mp4" : "jpg");
    const type =
      asset.mimeType ||
      (asset.type === "video" ? `video/${extension}` : IMAGE_MIME[extension] || "image/jpeg");
    onSendFile({
      uri: asset.uri,
      name: asset.fileName || `${asset.type === "video" ? "video" : "photo"}.${extension}`,
      type,
    });
  }

  /** iOS has a real action sheet; on Android the inline rows are the native shape. */
  function openAttachMenu() {
    if (Platform.OS !== "ios") {
      setSheetOpen((open) => !open);
      return;
    }
    ActionSheetIOS.showActionSheetWithOptions(
      {
        title: s.composer.sheetTitle,
        options: [s.composer.fromLibrary, s.composer.fromCamera, s.composer.cancel],
        cancelButtonIndex: 2,
      },
      (index) => {
        if (index === 0) pick("library");
        if (index === 1) pick("camera");
      },
    );
  }

  async function startRecording() {
    const permission = await AudioModule.requestRecordingPermissionsAsync();
    if (!permission.granted) {
      Alert.alert(s.composer.micDeniedTitle, s.composer.micDeniedBody);
      return;
    }
    setPreparing(true);
    try {
      // iOS refuses to record until the session allows it.
      await setAudioModeAsync({ allowsRecording: true, playsInSilentMode: true });
      if (!mounted.current) return;
      await recorder.prepareToRecordAsync();
      if (!mounted.current) return;
      setLevels(new Array(BARS).fill(0.08));
      setPaused(false);
      recorder.record();
    } catch {
      if (mounted.current) Alert.alert(s.composer.recordFailedTitle, s.composer.recordFailedBody);
    } finally {
      if (mounted.current) setPreparing(false);
    }
  }

  function togglePause() {
    try {
      if (paused) {
        recorder.record();
        setPaused(false);
      } else {
        recorder.pause();
        setPaused(true);
      }
    } catch {
      // A recorder that will not pause is still a recorder; leave it running.
    }
  }

  async function stopRecording(keep: boolean) {
    let uri: string | null = null;
    try {
      await recorder.stop();
      // Read the file before yielding again: the recorder is a native object
      // and this component may be on its way out.
      uri = recorder.uri;
      await setAudioModeAsync({ allowsRecording: false });
    } catch {
      return;
    } finally {
      if (mounted.current) setPaused(false);
    }
    if (!keep || !uri || !mounted.current) return;
    onSendFile({ uri, name: `voice-note.${extensionFor(uri, "m4a")}`, type: "audio/m4a" });
  }

  if (recording || preparing) {
    return (
      <View style={[styles.bar, styles.recordBar]}>
        <Pressable
          onPress={() => stopRecording(false)}
          hitSlop={10}
          style={({ pressed }) => [styles.iconButton, pressed && styles.pressed]}
          accessibilityRole="button"
          accessibilityLabel={s.composer.discardLabel}
        >
          <Ionicons name="trash-outline" size={22} color={colors.danger} />
        </Pressable>

        <View style={styles.recordBody}>
          <Animated.View style={[styles.recordDot, { backgroundColor: colors.danger, opacity: paused ? 0.3 : blink }]} />
          <Text style={[styles.recordTime, { color: colors.ink }]}>
            {preparing ? s.composer.recording : formatDuration(recorderState.durationMillis)}
          </Text>
          <Meter levels={levels} color={paused ? colors.subtle : brand} />
        </View>

        <Pressable
          onPress={togglePause}
          disabled={preparing}
          hitSlop={10}
          style={({ pressed }) => [styles.iconButton, (pressed || preparing) && styles.pressed]}
          accessibilityRole="button"
          accessibilityLabel={paused ? s.composer.resume : s.composer.pause}
        >
          <Ionicons name={paused ? "play" : "pause"} size={20} color={colors.muted} />
        </Pressable>

        <Pressable
          onPress={() => stopRecording(true)}
          disabled={preparing}
          style={({ pressed }) => [
            styles.circle,
            { backgroundColor: brand },
            (pressed || preparing) && styles.pressed,
          ]}
          accessibilityRole="button"
          accessibilityLabel={s.composer.sendVoice}
        >
          <Ionicons name="arrow-up" size={20} color={contrastOn(brand)} />
        </Pressable>
      </View>
    );
  }

  return (
    <View>
      {sheetOpen && Platform.OS !== "ios" ? (
        <View style={[styles.sheet, { borderTopColor: colors.line, backgroundColor: colors.surface }]}>
          {[
            { label: s.composer.fromLibrary, action: () => pick("library") },
            { label: s.composer.fromCamera, action: () => pick("camera") },
          ].map((option) => (
            <Pressable
              key={option.label}
              onPress={option.action}
              android_ripple={{ color: colors.pressed }}
              style={({ pressed }) => [styles.sheetRow, pressed && { backgroundColor: tint(brand, 0.08) }]}
              accessibilityRole="button"
            >
              <Text style={[styles.sheetText, { color: colors.ink }]}>{option.label}</Text>
            </Pressable>
          ))}
        </View>
      ) : null}

      <View style={styles.bar}>
        <Pressable
          onPress={openAttachMenu}
          hitSlop={8}
          style={({ pressed }) => [styles.iconButton, pressed && styles.pressed]}
          accessibilityRole="button"
          accessibilityLabel={s.composer.attach}
        >
          <Ionicons name="add" size={28} color={sheetOpen ? brand : colors.muted} />
        </Pressable>

        <TextInput
          style={[styles.input, { borderColor: colors.line, color: colors.ink, backgroundColor: colors.canvas }]}
          value={draft}
          onChangeText={setDraft}
          placeholder={s.composer.placeholder}
          placeholderTextColor={colors.subtle}
          multiline
          onFocus={() => setSheetOpen(false)}
        />

        {canSend ? (
          <Pressable
            onPress={send}
            disabled={busy}
            style={({ pressed }) => [styles.circle, { backgroundColor: brand }, pressed && styles.pressed]}
            accessibilityRole="button"
            accessibilityLabel={s.composer.send}
          >
            {busy ? (
              <ActivityIndicator size="small" color={contrastOn(brand)} />
            ) : (
              <Ionicons name="arrow-up" size={20} color={contrastOn(brand)} />
            )}
          </Pressable>
        ) : (
          <>
            <Pressable
              onPress={() => pick("camera")}
              disabled={busy}
              hitSlop={8}
              style={({ pressed }) => [styles.iconButton, pressed && styles.pressed]}
              accessibilityRole="button"
              accessibilityLabel={s.composer.fromCamera}
            >
              <Ionicons name="camera-outline" size={24} color={colors.muted} />
            </Pressable>
            <Pressable
              onPress={startRecording}
              disabled={busy}
              hitSlop={8}
              style={({ pressed }) => [styles.iconButton, pressed && styles.pressed]}
              accessibilityRole="button"
              accessibilityLabel={s.composer.record}
            >
              <Ionicons name="mic-outline" size={24} color={colors.muted} />
            </Pressable>
          </>
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  bar: { flexDirection: "row", alignItems: "flex-end", gap: 4, paddingHorizontal: 8, paddingVertical: 8 },
  recordBar: { alignItems: "center", gap: 8 },
  iconButton: { width: 38, height: 38, alignItems: "center", justifyContent: "center" },
  input: {
    flex: 1,
    minHeight: 38,
    maxHeight: 120,
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: 19,
    paddingHorizontal: 15,
    paddingTop: Platform.OS === "ios" ? 9 : 6,
    paddingBottom: Platform.OS === "ios" ? 9 : 6,
    fontSize: 16,
    lineHeight: 20,
  },
  circle: { width: 38, height: 38, borderRadius: 19, alignItems: "center", justifyContent: "center" },
  pressed: { opacity: 0.55 },
  sheet: { borderTopWidth: StyleSheet.hairlineWidth },
  sheetRow: { paddingVertical: 15, paddingHorizontal: 20 },
  sheetText: { fontSize: 16 },
  recordBody: { flex: 1, flexDirection: "row", alignItems: "center", gap: 8, height: 38 },
  recordDot: { width: 9, height: 9, borderRadius: 5 },
  recordTime: { fontSize: 15, fontVariant: ["tabular-nums"], minWidth: 42 },
  meter: { flex: 1, flexDirection: "row", alignItems: "center", gap: 2, height: 26 },
  meterBar: { flex: 1, borderRadius: 1.5, minHeight: 4 },
});
