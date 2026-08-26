/**
 * Writing back: text, a photo, a file, or a voice note.
 *
 * The set of things you can send is deliberately what someone answering from
 * WhatsApp would reach for, and no more. Recording replaces the composer with a
 * running timer while it is held open, because a half-recorded voice note that
 * looks like a text field is the fastest way to send silence.
 */

import { useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import * as ImagePicker from "expo-image-picker";
import {
  AudioModule,
  RecordingPresets,
  setAudioModeAsync,
  useAudioRecorder,
  useAudioRecorderState,
} from "expo-audio";
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

export function Composer({ brand, busy, onSendText, onSendFile }: Props) {
  const colors = useColors();
  const [draft, setDraft] = useState("");
  const [sheetOpen, setSheetOpen] = useState(false);
  const recorder = useAudioRecorder(RecordingPresets.HIGH_QUALITY);
  const recorderState = useAudioRecorderState(recorder);
  const [preparing, setPreparing] = useState(false);
  const cancelled = useRef(false);

  const recording = recorderState.isRecording;
  const canSend = draft.trim().length > 0 && !busy;

  useEffect(() => {
    return () => {
      // Leaving mid-recording must not leave the microphone open.
      if (recorder.isRecording) recorder.stop().catch(() => {});
    };
  }, [recorder]);

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
        from === "camera" ? "Camera access is off" : "Photo access is off",
        "Turn it on in Settings to send photos from here.",
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

  async function startRecording() {
    const permission = await AudioModule.requestRecordingPermissionsAsync();
    if (!permission.granted) {
      Alert.alert("Microphone access is off", "Turn it on in Settings to send voice notes.");
      return;
    }
    setPreparing(true);
    try {
      // iOS refuses to record until the session allows it.
      await setAudioModeAsync({ allowsRecording: true, playsInSilentMode: true });
      await recorder.prepareToRecordAsync();
      cancelled.current = false;
      recorder.record();
    } catch {
      Alert.alert("Could not start recording", "Try again in a moment.");
    } finally {
      setPreparing(false);
    }
  }

  async function stopRecording(keep: boolean) {
    cancelled.current = !keep;
    try {
      await recorder.stop();
      await setAudioModeAsync({ allowsRecording: false });
    } catch {
      return;
    }
    const uri = recorder.uri;
    if (!keep || !uri) return;
    const extension = extensionFor(uri, Platform.OS === "ios" ? "m4a" : "m4a");
    onSendFile({ uri, name: `voice-note.${extension}`, type: "audio/m4a" });
  }

  if (recording || preparing) {
    return (
      <View style={styles.bar}>
        <Pressable
          onPress={() => stopRecording(false)}
          style={({ pressed }) => [styles.recordCancel, pressed && styles.pressed]}
          accessibilityRole="button"
          accessibilityLabel="Discard recording"
        >
          <Text style={[styles.recordCancelText, { color: colors.muted }]}>Cancel</Text>
        </Pressable>
        <View style={styles.recordMeter}>
          <View style={[styles.recordDot, { backgroundColor: colors.danger }]} />
          <Text style={[styles.recordTime, { color: colors.ink }]}>
            {preparing ? "Starting…" : formatDuration(recorderState.durationMillis)}
          </Text>
        </View>
        <Pressable
          onPress={() => stopRecording(true)}
          disabled={preparing}
          style={({ pressed }) => [
            styles.circle,
            { backgroundColor: brand },
            (pressed || preparing) && styles.pressed,
          ]}
          accessibilityRole="button"
          accessibilityLabel="Send voice note"
        >
          <Text style={[styles.circleGlyph, { color: contrastOn(brand) }]}>↑</Text>
        </Pressable>
      </View>
    );
  }

  return (
    <View>
      {sheetOpen ? (
        <View style={[styles.sheet, { borderTopColor: colors.line, backgroundColor: colors.surface }]}>
          {[
            { label: "Photo or video", action: () => pick("library") },
            { label: "Take a photo", action: () => pick("camera") },
          ].map((option) => (
            <Pressable
              key={option.label}
              onPress={option.action}
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
          onPress={() => setSheetOpen((open) => !open)}
          hitSlop={8}
          style={({ pressed }) => [styles.attach, pressed && styles.pressed]}
          accessibilityRole="button"
          accessibilityLabel="Add an attachment"
        >
          <Text style={[styles.attachGlyph, { color: colors.muted }, sheetOpen && { color: brand }]}>+</Text>
        </Pressable>

        <TextInput
          style={[styles.input, { borderColor: colors.line, color: colors.ink, backgroundColor: colors.canvas }]}
          value={draft}
          onChangeText={setDraft}
          placeholder="Message"
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
            accessibilityLabel="Send"
          >
            {busy ? (
              <ActivityIndicator size="small" color={contrastOn(brand)} />
            ) : (
              <Text style={[styles.circleGlyph, { color: contrastOn(brand) }]}>↑</Text>
            )}
          </Pressable>
        ) : (
          <Pressable
            onPress={startRecording}
            disabled={busy}
            style={({ pressed }) => [styles.circleGhost, pressed && styles.pressed]}
            accessibilityRole="button"
            accessibilityLabel="Record a voice note"
          >
            <Text style={[styles.micGlyph, { color: colors.muted }]}>●</Text>
          </Pressable>
        )}
      </View>
    </View>
  );
}

function formatDuration(millis: number | undefined): string {
  const total = Math.floor((millis || 0) / 1000);
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}

const styles = StyleSheet.create({
  bar: { flexDirection: "row", alignItems: "flex-end", gap: 8, paddingHorizontal: 10, paddingVertical: 8 },
  attach: { width: 36, height: 36, alignItems: "center", justifyContent: "center" },
  attachGlyph: { fontSize: 26, lineHeight: 30, fontWeight: "300" },
  input: {
    flex: 1,
    minHeight: 36,
    maxHeight: 120,
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: 18,
    paddingHorizontal: 14,
    paddingTop: Platform.OS === "ios" ? 9 : 6,
    paddingBottom: Platform.OS === "ios" ? 9 : 6,
    fontSize: 16,
    lineHeight: 20,
  },
  circle: { width: 36, height: 36, borderRadius: 18, alignItems: "center", justifyContent: "center" },
  circleGhost: {
    width: 36,
    height: 36,
    borderRadius: 18,
    alignItems: "center",
    justifyContent: "center",
  },
  circleGlyph: { fontSize: 18, lineHeight: 21, fontWeight: "600" },
  micGlyph: { fontSize: 17 },
  pressed: { opacity: 0.55 },
  sheet: { borderTopWidth: StyleSheet.hairlineWidth },
  sheetRow: { paddingVertical: 14, paddingHorizontal: 20 },
  sheetText: { fontSize: 16 },
  recordCancel: { height: 36, justifyContent: "center", paddingHorizontal: 6 },
  recordCancelText: { fontSize: 15 },
  recordMeter: { flex: 1, flexDirection: "row", alignItems: "center", gap: 8, height: 36 },
  recordDot: { width: 9, height: 9, borderRadius: 5 },
  recordTime: { fontSize: 15, fontVariant: ["tabular-nums"] },
});
