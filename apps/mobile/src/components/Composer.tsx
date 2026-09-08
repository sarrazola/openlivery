/**
 * Writing back: text, a photo, a file, or a voice note.
 *
 * Saved replies sit above the message field. The attachment menu and microphone
 * sit to its left, with sending on the right. Recording stays available with
 * text already written; the attachment menu also provides camera access.
 *
 * Recording replaces the whole row - a level meter, the elapsed time, and
 * delete / pause / review. Review stages the original audio as an attachment
 * with playback so the user can listen before sending it with their text.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import {
  ActionSheetIOS,
  ActivityIndicator,
  Alert,
  AppState,
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
import * as DocumentPicker from "expo-document-picker";
import { Image } from "expo-image";
import { chatStrings } from "../chatStrings";
import type { ChannelCapabilities } from "../api";
import { acceptsAttachment, channelCapabilities } from "../inbox";
import { createRecordingSession, RecordingUnavailableError } from "../recordingSession";
import { setRecordingMode } from "../audioSession";
import { LocalAudioPreview } from "./Attachments";
import {
  AudioModule,
  RecordingPresets,
  useAudioRecorder,
  useAudioRecorderState,
} from "expo-audio";
import { useStrings } from "../i18n";
import { contrastOn, tint, useColors } from "../theme";

export type OutgoingFile = { uri: string; name: string; type: string };

type Draft = { text: string; file: OutgoingFile | null };
const sessionDrafts = new Map<string, Draft>();
let draftSessionEpoch = 0;
/** Called when a session ends; drafts never persist to disk. */
export function clearComposerDrafts() { sessionDrafts.clear(); draftSessionEpoch += 1; }

type Props = {
  draftKey: string;
  brand: string;
  busy: boolean;
  channel?: string;
  capabilities?: ChannelCapabilities;
  onSendText: (text: string) => Promise<boolean>;
  onSendFile: (file: OutgoingFile, caption: string) => Promise<boolean>;
  insertedReply?: { text: string; key: number } | null;
  onReplyInserted?: (key: number) => void;
  onSavedReplies?: () => void;
  onAttachmentSelected?: () => void;
  onError: (message: string) => void;
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

export function Composer({ draftKey, brand, busy, channel = "widget", capabilities = channelCapabilities({ channel }), onSendText, onSendFile, insertedReply, onReplyInserted, onSavedReplies, onAttachmentSelected, onError }: Props) {
  const colors = useColors();
  const s = useStrings();
  const c = chatStrings();
  const [pendingFile, setPendingFile] = useState<OutgoingFile | null>(() => sessionDrafts.get(draftKey)?.file || null);
  const sending = useRef(false);
  const recordingEpoch = useRef(0);
  const preparingRef = useRef(false);
  const stoppingRef = useRef(false);
  const changingPause = useRef(false);
  const [stopping, setStopping] = useState(false);
  const input = useRef<TextInput>(null);
  const [draft, setDraft] = useState(() => sessionDrafts.get(draftKey)?.text || "");

  useEffect(() => {
    if (draft || pendingFile) {
      sessionDrafts.set(draftKey, { text: draft, file: pendingFile });
      if (sessionDrafts.size > 50) sessionDrafts.delete(sessionDrafts.keys().next().value!);
    } else sessionDrafts.delete(draftKey);
  }, [draftKey, draft, pendingFile]);
  const [sheetOpen, setSheetOpen] = useState(false);
  const recorder = useAudioRecorder({ ...RecordingPresets.HIGH_QUALITY, isMeteringEnabled: true });
  const recorderState = useAudioRecorderState(recorder, METER_INTERVAL_MS);
  const recordingSession = useMemo(() => createRecordingSession({
    record: () => recorder.record(), pause: () => recorder.pause(), stop: () => recorder.stop(),
    isRecording: () => recorder.isRecording, duration: () => recorder.currentTime,
    uri: () => recorder.uri, enable: setRecordingMode,
  }), [recorder]);
  const [preparing, setPreparing] = useState(false);
  const [paused, setPaused] = useState(false);
  const [levels, setLevels] = useState<number[]>(() => new Array(BARS).fill(0.08));
  const blink = useRef(new Animated.Value(1)).current;

  const recording = recorderState.isRecording || paused;
  const textAllowed = capabilities.text === true;
  const fileAllowed = !pendingFile || acceptsAttachment(channel, capabilities, pendingFile.type);
  const canSend = fileAllowed && (!draft.trim() || textAllowed) && (draft.trim().length > 0 || Boolean(pendingFile));
  const canAttach = [capabilities.image, capabilities.video, capabilities.audio, capabilities.file].some(Boolean);
  const attachmentOptions = [
    ...(capabilities.image || capabilities.video ? [{ label: s.composer.fromLibrary, source: "library" as const }, { label: s.composer.fromCamera, source: "camera" as const }] : []),
    ...(canAttach ? [{ label: c.file, source: "file" as const }] : []),
  ];

  useEffect(() => { if (pendingFile) onAttachmentSelected?.(); }, [pendingFile, onAttachmentSelected]);

  useEffect(() => {
    if (insertedReply) {
      setDraft(insertedReply.text);
      input.current?.focus();
      onReplyInserted?.(insertedReply.key);
    }
  }, [insertedReply, onReplyInserted]);

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
      recordingEpoch.current += 1;
    };
  }, []);

  async function send() {
    if (!canSend || busy || sending.current) return;
    sending.current = true;
    const submitted = { text: draft, file: pendingFile };
    const sessionEpoch = draftSessionEpoch;
    try {
      const text = draft.trim();
      const sent = pendingFile ? await onSendFile(pendingFile, text) : await onSendText(text);
      if (sent) {
        // API success can arrive after navigation unmounted this composer. Clear
        // the matching saved draft immediately without erasing a newer draft.
        const current = sessionDrafts.get(draftKey);
        if (sessionEpoch === draftSessionEpoch && current?.text === submitted.text && current.file?.uri === submitted.file?.uri) sessionDrafts.delete(draftKey);
        if (mounted.current) {
          setDraft((currentText) => currentText === submitted.text ? "" : currentText);
          setPendingFile((currentFile) => currentFile?.uri === submitted.file?.uri ? null : currentFile);
        }
      }
    } catch (error) { if (mounted.current) onError(error instanceof Error ? error.message : s.chat.sendFailed); } finally { sending.current = false; }
  }

  async function pick(from: "library" | "camera" | "file") {
    if (busy || sending.current || !canAttach || (from !== "file" && !capabilities.image && !capabilities.video)) return;
    setSheetOpen(false);
    try {
      if (from === "file") {
        const types = capabilities.file && channel !== "instagram" ? ["*/*"] : [
          ...(capabilities.image ? ["image/*"] : []), ...(capabilities.video ? ["video/*"] : []),
          ...(capabilities.audio ? ["audio/*"] : []), ...(capabilities.file ? ["application/pdf"] : []),
        ];
        const result = await DocumentPicker.getDocumentAsync({ type: types, copyToCacheDirectory: true, multiple: false });
        if (!result.canceled && result.assets?.[0] && mounted.current) {
          const asset = result.assets[0];
          if (!acceptsAttachment(channel, capabilities, asset.mimeType || "application/octet-stream")) { onError(c.unsupportedAttachment); return; }
          setPendingFile({ uri: asset.uri, name: asset.name, type: asset.mimeType || "application/octet-stream" });
        }
        return;
      }
      const permission = from === "camera" ? await ImagePicker.requestCameraPermissionsAsync() : { granted: true };
      if (!permission.granted) {
        Alert.alert(s.composer.cameraDeniedTitle, s.composer.mediaDeniedBody);
        return;
      }
      const options: ImagePicker.ImagePickerOptions = {
        mediaTypes: [...(capabilities.image ? ["images" as const] : []), ...(capabilities.video ? ["videos" as const] : [])], quality: 0.8, allowsMultipleSelection: false,
      };
      const result = from === "camera" ? await ImagePicker.launchCameraAsync(options) : await ImagePicker.launchImageLibraryAsync(options);
      if (result.canceled || !result.assets?.length || !mounted.current) return;
      const asset = result.assets[0];
      const extension = extensionFor(asset.uri, asset.type === "video" ? "mp4" : "jpg");
      const type = asset.mimeType || (asset.type === "video" ? `video/${extension}` : IMAGE_MIME[extension] || "image/jpeg");
      if (!acceptsAttachment(channel, capabilities, type)) { onError(c.unsupportedAttachment); return; }
      setPendingFile({ uri: asset.uri, name: asset.fileName || `${asset.type === "video" ? "video" : "photo"}.${extension}`, type });
    } catch (error) {
      if (mounted.current) onError(error instanceof Error ? error.message : c.pickFailed);
    }
  }

  /** iOS has a real action sheet; on Android the inline rows are the native shape. */
  function openAttachMenu() {
    if (busy || stopping || !canAttach) return;
    if (Platform.OS !== "ios") {
      setSheetOpen((open) => !open);
      return;
    }
    ActionSheetIOS.showActionSheetWithOptions(
      {
        title: s.composer.sheetTitle,
        options: [...attachmentOptions.map((option) => option.label), s.composer.cancel],
        cancelButtonIndex: attachmentOptions.length,
      },
      (index) => {
        const option = attachmentOptions[index];
        if (option) void pick(option.source);
      },
    );
  }

  async function startRecording() {
    if (busy || !capabilities.audio || preparingRef.current || stoppingRef.current) return;
    preparingRef.current = true;
    const epoch = ++recordingEpoch.current;
    setPreparing(true);
    let started = false;
    try {
      const permission = await AudioModule.requestRecordingPermissionsAsync();
      if (!mounted.current || epoch !== recordingEpoch.current) return;
      if (!permission.granted) {
        Alert.alert(s.composer.micDeniedTitle, s.composer.micDeniedBody);
        return;
      }
      await setRecordingMode(true);
      if (!mounted.current || epoch !== recordingEpoch.current) return;
      await recorder.prepareToRecordAsync();
      if (!mounted.current) return;
      if (epoch !== recordingEpoch.current) { await recorder.stop(); return; }
      setLevels(new Array(BARS).fill(0.08));
      setPaused(false);
      recordingSession.start();
      started = true;
    } catch (error) {
      if (recordingSession.isActive()) {
        try { await recordingSession.finish(); } catch {}
      }
      if (mounted.current && epoch === recordingEpoch.current) Alert.alert(s.composer.recordFailedTitle, error instanceof RecordingUnavailableError ? c.micUnavailable : s.composer.recordFailedBody);
    } finally {
      preparingRef.current = false;
      if (mounted.current) setPreparing(false);
      if (!started || epoch !== recordingEpoch.current) void setRecordingMode(false).catch(() => {});
    }
  }

  async function togglePause() {
    if (changingPause.current || stoppingRef.current) return;
    changingPause.current = true;
    try {
      if (recordingSession.isPaused()) await recordingSession.resume();
      else await recordingSession.pause();
    } catch { if (mounted.current) onError(c.recordFailed); }
    finally {
      changingPause.current = false;
      if (mounted.current) setPaused(recordingSession.isPaused());
    }
  }

  async function stopRecording(action: "discard" | "preserve") {
    if (preparingRef.current) {
      recordingEpoch.current += 1; setPreparing(false);
      return;
    }
    if (stoppingRef.current || sending.current) return;
    stoppingRef.current = true;
    setStopping(true);
    const sessionEpoch = draftSessionEpoch;
    try {
      const uri = await recordingSession.finish();
      if (action === "discard" || !uri || sessionEpoch !== draftSessionEpoch) return;
      if (recordingSession.duration() < 0.3) {
        if (mounted.current) onError(c.recordingTooShort);
        return;
      }
      const file = { uri, name: `voice-note.${extensionFor(uri, "m4a")}`, type: "audio/mp4" };
      // Preserve an interrupted note even if navigation unmounted the screen
      // while the native recorder was finalizing its file. Never auto-send it.
      sessionDrafts.set(draftKey, { text: draft, file });
      if (!mounted.current) return;
      setPendingFile(file);
    } catch (error) {
      if (mounted.current) onError(error instanceof Error ? error.message : c.recordFailed);
    } finally {
      sending.current = false;
      stoppingRef.current = false;
      if (mounted.current) { setPaused(false); setStopping(false); }
    }
  }

  const interruptRecording = useRef(() => {});
  interruptRecording.current = () => { void stopRecording("preserve"); };
  useEffect(() => {
    const subscription = AppState.addEventListener("change", (state) => {
      if (state === "active") return;
      // Permission prompts can make the app inactive before recording starts.
      // Preserve a running/paused note on any interruption, but only cancel a
      // pending preparation when the user actually backgrounds the app.
      if (recordingSession.isActive() || state === "background") interruptRecording.current();
    });
    return () => subscription.remove();
  }, [recordingSession]);

  if (recording || preparing) {
    return (
      <View style={[styles.bar, styles.recordBar]}>
        <Pressable
          onPress={() => stopRecording("discard")}
          disabled={stopping}
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
          disabled={preparing || stopping}
          hitSlop={10}
          style={({ pressed }) => [styles.iconButton, (pressed || preparing) && styles.pressed]}
          accessibilityRole="button"
          accessibilityLabel={paused ? s.composer.resume : s.composer.pause}
        >
          <Ionicons name={paused ? "play" : "pause"} size={20} color={colors.muted} />
        </Pressable>

        <Pressable
          onPress={() => stopRecording("preserve")}
          disabled={preparing || stopping}
          style={({ pressed }) => [
            styles.reviewRecording,
            { backgroundColor: brand },
            (pressed || preparing) && styles.pressed,
          ]}
          accessibilityRole="button"
          accessibilityLabel={c.reviewAudio}
        >
          <Ionicons name="stop" size={16} color={contrastOn(brand)} />
          <Text style={{ color: contrastOn(brand), fontWeight: "700", fontSize: 12 }}>{c.review}</Text>
        </Pressable>
      </View>
    );
  }

  return (
    <View>
      {pendingFile ? <View style={{ borderBottomColor: colors.line, borderBottomWidth: StyleSheet.hairlineWidth }}><View style={styles.pending}>
        {pendingFile.type.startsWith("image/") ? <Image source={{ uri: pendingFile.uri }} style={styles.thumbnail} contentFit="cover" /> : <Ionicons name={pendingFile.type.startsWith("audio/") ? "mic-outline" : "document-attach-outline"} size={26} color={brand} />}
        <View style={{ flex: 1 }}><Text numberOfLines={1} style={{ color: colors.ink, fontWeight: "600" }}>{pendingFile.type.startsWith("audio/") ? c.audioReady : pendingFile.name}</Text><Text style={{ color: colors.muted, fontSize: 12 }}>{c.attached}</Text></View>
        <Pressable disabled={busy} onPress={() => setPendingFile(null)} style={styles.iconButton} accessibilityRole="button" accessibilityLabel={c.removeFile}><Ionicons name="close-circle" size={24} color={colors.muted} /></Pressable>
      </View>{pendingFile.type.startsWith("audio/") ? <View style={{ paddingHorizontal: 14, paddingBottom: 12 }}><LocalAudioPreview uri={pendingFile.uri} brand={brand} /></View> : null}</View> : null}
      {pendingFile && !fileAllowed && <Text accessibilityRole="alert" style={{ color: colors.danger, fontSize: 12, paddingHorizontal: 14 }}>{c.unsupportedAttachment}</Text>}
      <View style={styles.shortcuts}>
        {onSavedReplies && textAllowed ? <Pressable onPress={onSavedReplies} disabled={busy || stopping} style={styles.shortcut} accessibilityRole="button"><Ionicons name="flash-outline" size={17} color={brand} /><Text style={{ color: brand, fontSize: 12, fontWeight: "600" }}>{c.canned}</Text></Pressable> : null}
      </View>
      {sheetOpen && Platform.OS !== "ios" ? (
        <View style={[styles.sheet, { borderTopColor: colors.line, backgroundColor: colors.surface }]}>
          {attachmentOptions.map((option) => (
            <Pressable
              key={option.label}
              onPress={() => void pick(option.source)}
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
          disabled={busy || stopping || !canAttach}
          hitSlop={8}
          style={({ pressed }) => [styles.iconButton, pressed && styles.pressed]}
          accessibilityRole="button"
          accessibilityLabel={s.composer.attach}
        >
          <Ionicons name="add" size={28} color={sheetOpen ? brand : colors.muted} />
        </Pressable>

        <Pressable
          onPress={startRecording}
          disabled={busy || stopping || !capabilities.audio || Boolean(pendingFile)}
          style={({ pressed }) => [styles.recordButton, pressed && styles.pressed, pendingFile && { opacity: .5 }]}
          accessibilityRole="button"
          accessibilityLabel={c.recordAudio}
          accessibilityState={{ disabled: busy || stopping || !capabilities.audio || Boolean(pendingFile) }}
        >
          <Ionicons name="mic-outline" size={22} color={colors.muted} />
        </Pressable>

        <TextInput
          ref={input}
          editable={!busy && !stopping && textAllowed}
          accessibilityLabel={pendingFile ? c.caption : s.composer.placeholder}
          style={[styles.input, { borderColor: colors.line, color: colors.ink, backgroundColor: colors.canvas }]}
          value={draft}
          onChangeText={setDraft}
          placeholder={pendingFile ? c.caption : s.composer.placeholder}
          placeholderTextColor={colors.subtle}
          multiline
          onFocus={() => setSheetOpen(false)}
        />

        {canSend ? (
          <Pressable
            onPress={send}
            disabled={busy || stopping}
            style={({ pressed }) => [styles.circle, { backgroundColor: brand }, pressed && styles.pressed]}
            accessibilityRole="button"
            accessibilityLabel={pendingFile?.type.startsWith("audio/") ? s.composer.sendVoice : s.composer.send}
          >
            {busy ? (
              <ActivityIndicator size="small" color={contrastOn(brand)} />
            ) : (
              <Ionicons name="arrow-up" size={20} color={contrastOn(brand)} />
            )}
          </Pressable>
        ) : null}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  pending: { flexDirection: "row", alignItems: "center", gap: 12, padding: 12 },
  thumbnail: { width: 44, height: 44, borderRadius: 8 },
  shortcuts: { flexDirection: "row", flexWrap: "wrap", gap: 8, paddingHorizontal: 12, paddingTop: 6 },
  shortcut: { flexDirection: "row", alignItems: "center", gap: 6, minHeight: 44, paddingHorizontal: 10, borderRadius: 10 },
  reviewRecording: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 5, minHeight: 44, paddingHorizontal: 10, borderRadius: 22 },
  bar: { flexDirection: "row", alignItems: "flex-end", gap: 4, paddingHorizontal: 8, paddingVertical: 8 },
  recordBar: { alignItems: "center", gap: 8 },
  iconButton: { width: 38, height: 38, alignItems: "center", justifyContent: "center" },
  recordButton: { width: 44, height: 44, alignItems: "center", justifyContent: "center" },
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
