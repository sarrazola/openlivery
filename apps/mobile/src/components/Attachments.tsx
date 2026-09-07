/**
 * Rendering what came in with a message.
 *
 * Attachments live behind the portal session, so none of them can be a plain
 * URL in a src: every fetch carries the bearer token. Images render inline,
 * voice notes get a play button and a track, and anything else falls back to a
 * row you can tap to open.
 */

import { useEffect, useMemo, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  Modal,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { SafeAreaView } from "react-native-safe-area-context";
import { Image } from "expo-image";
import * as Sharing from "expo-sharing";
import { chatStrings } from "../chatStrings";
import { prepareAudioPlayback } from "../audioSession";
import { Directory, File, Paths } from "expo-file-system";
import { useAudioPlayer, useAudioPlayerStatus } from "expo-audio";
import { attachmentUrl, authHeaders, type Attachment, type Session } from "../api";
import { useStrings, type Strings } from "../i18n";
import { contrastOn, useColors, type Colors } from "../theme";

function clock(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return "0:00";
  const total = Math.floor(seconds);
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}

export function humanSize(bytes: number): string {
  if (!bytes) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

type Props = {
  attachment: Attachment;
  server: string;
  session: Session;
  conversationId: string;
  outgoing: boolean;
  /** The colour the outgoing bubble is painted, needed for contrast. */
  brand: string;
};

function ImageAttachment({
  url,
  headers,
  colors,
  s,
}: {
  url: string;
  headers: Record<string, string>;
  colors: Colors;
  s: Strings;
}) {
  const [failed, setFailed] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const c = chatStrings();
  if (failed) {
    return (
      <Pressable onPress={() => setFailed(false)} style={[styles.broken, { backgroundColor: colors.bubbleIn }]} accessibilityRole="button" accessibilityLabel={c.attachmentRetry}>
        <Text style={[styles.brokenText, { color: colors.muted }]}>{s.attachment.imageUnavailable}</Text><Text style={{ color: colors.ink, marginTop: 8 }}>{c.retry}</Text>
      </Pressable>
    );
  }
  return (
    <>
    <Pressable onPress={() => setExpanded(true)} accessibilityRole="button" accessibilityLabel={c.viewImage}>
    <Image
      source={{ uri: url, headers }}
      style={styles.image}
      contentFit="cover"
      transition={120}
      onError={() => setFailed(true)}
      accessibilityLabel={s.attachment.image}
    />
    </Pressable>
    <Modal visible={expanded} animationType="fade" onRequestClose={() => setExpanded(false)}>
      <SafeAreaView style={{ flex: 1, backgroundColor: colors.surface }}>
        <Pressable onPress={() => setExpanded(false)} accessibilityRole="button" accessibilityLabel={c.close} style={{ alignSelf: "flex-end", padding: 18 }}><Ionicons name="close" size={28} color={colors.ink} /></Pressable>
        <Image source={{ uri: url, headers }} style={{ flex: 1 }} contentFit="contain" accessibilityLabel={s.attachment.image} />
      </SafeAreaView>
    </Modal>
    </>
  );
}

/**
 * Fetch an attachment into the cache once and hand back its local path.
 *
 * The audio player asks for byte ranges as it goes, and those requests do not
 * carry the session, so streaming a credentialed URL stalls. Downloading first
 * sidesteps that and means replaying costs nothing.
 */
async function downloadAttachment(url: string, headers: Record<string, string>, id: string, extension: string, force = false): Promise<string> {
  const folder = new Directory(Paths.cache, "attachments");
  if (!folder.exists) folder.create({ intermediates: true });
  // The URL contains the server and portal, so caches remain isolated even
  // when two installations happen to reuse the same attachment identifier.
  let hash = 2166136261;
  for (const char of url) hash = Math.imul(hash ^ char.charCodeAt(0), 16777619);
  const target = new File(folder, `${(hash >>> 0).toString(16)}-${id}.${extension}`);
  if (force && target.exists) target.delete();
  if (target.exists && target.size > 0) return target.uri;
  try {
    await File.downloadFileAsync(url, target, { headers, idempotent: true });
    return target.uri;
  } catch (error) {
    // Android may leave a partial download. Never reuse a failed transfer.
    if (target.exists) target.delete();
    throw error;
  }
}

function useCachedAudio(url: string, headers: Record<string, string>, id: string, extension: string) {
  const [path, setPath] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const authorization = headers.Authorization;
  useEffect(() => {
    let cancelled = false;
    setFailed(false);
    setPath(null);
    downloadAttachment(url, { Authorization: authorization }, id, extension, attempt > 0)
      .then((uri) => { if (!cancelled) setPath(uri); })
      .catch(() => { if (!cancelled) setFailed(true); });
    return () => { cancelled = true; };
  }, [url, id, extension, authorization, attempt]);
  return { path, failed, retry: () => setAttempt((value) => value + 1) };
}

/**
 * The playable half of a voice note.
 *
 * Split from the component that downloads it, and mounted only once the file
 * is on disk, so the source it is given never changes. That matters more than
 * it looks: useAudioPlayer releases its native player and builds a new one
 * whenever the source changes, and useAudioPlayerStatus reads the player it
 * was handed - so a source that goes from nothing to a path leaves a window
 * where the status hook can touch an object that has just been freed, which
 * takes the whole app down. Mounting late closes the window instead of racing
 * it.
 */
function VoiceNote({
  onRetry,
  uri,
  control,
  onControl,
  s,
}: {
  onRetry: () => void;
  uri: string;
  /** The filled button and the played part of the track. */
  control: string;
  /** The glyph drawn on top of `control`. */
  onControl: string;
  s: Strings;
}) {
  // Memoised so a re-render never looks like a new source.
  const source = useMemo(() => ({ uri }), [uri]);
  const player = useAudioPlayer(source);
  const status = useAudioPlayerStatus(player);
  const c = chatStrings();
  const [playbackError, setPlaybackError] = useState(false);
  useEffect(() => {
    if (status.isLoaded) return;
    const timer = setTimeout(() => setPlaybackError(true), 15000);
    return () => clearTimeout(timer);
  }, [status.isLoaded]);
  if (status.error || playbackError) return <Pressable onPress={onRetry} accessibilityRole="button" accessibilityLabel={c.attachmentRetry} style={{ padding: 10 }}><Text style={{ color: control }}>{c.audioFailed}</Text><Text style={{ color: control, fontWeight: "600", marginTop: 4 }}>{c.retry}</Text></Pressable>;

  const playing = status.playing;
  const duration = status.duration || 0;
  const elapsed = status.currentTime || 0;
  const progress = duration > 0 ? Math.min(elapsed / duration, 1) : 0;

  return (
    <Row
      control={control}
      onControl={onControl}
      busy={!status.isLoaded || (status.isBuffering && !playing)}
      playing={playing}
      progress={progress}
      label={clock(playing || elapsed > 0 ? elapsed : duration)}
      accessibilityLabel={playing ? s.attachment.pause : s.attachment.play}
      onPress={async () => {
        try {
        if (playing) {
          player.pause();
          return;
        }
        await prepareAudioPlayback();
        // Replaying after it ended needs an explicit rewind.
        if (duration > 0 && elapsed >= duration - 0.15) await player.seekTo(0);
        player.play();
        } catch { setPlaybackError(true); }
      }}
    />
  );
}

export function LocalAudioPreview({ uri, brand }: { uri: string; brand: string }) {
  const [attempt, setAttempt] = useState(0);
  return <VoiceNote key={`${uri}:${attempt}`} uri={uri} control={brand} onControl={contrastOn(brand)} s={useStrings()} onRetry={() => setAttempt((value) => value + 1)} />;
}

/** The voice-note layout, shared by the loading and playable states. */
function Row({
  control,
  onControl,
  busy,
  playing,
  progress,
  label,
  accessibilityLabel,
  onPress,
}: {
  control: string;
  onControl: string;
  busy: boolean;
  playing: boolean;
  progress: number;
  label: string;
  accessibilityLabel?: string;
  onPress?: () => void;
}) {
  return (
    <View style={styles.audio}>
      <Pressable
        onPress={onPress}
        disabled={!onPress}
        hitSlop={8}
        style={({ pressed }) => [styles.playButton, { backgroundColor: control }, pressed && styles.pressed]}
        accessibilityRole="button"
        accessibilityLabel={accessibilityLabel}
      >
        {busy ? (
          <ActivityIndicator size="small" color={onControl} />
        ) : (
          <Ionicons name={playing ? "pause" : "play"} size={16} color={onControl} />
        )}
      </Pressable>
      <View style={styles.audioBody}>
        <View style={[styles.track, { backgroundColor: control, opacity: 0.3 }]} />
        <View style={[styles.trackFill, { width: `${progress * 100}%`, backgroundColor: control }]} />
        <Text style={[styles.audioTime, { color: control }]}>{label}</Text>
      </View>
    </View>
  );
}

export function AttachmentView({ attachment, server, session, conversationId, outgoing, brand }: Props) {
  const colors = useColors();
  const s = useStrings();
  const c = chatStrings();
  const [opening, setOpening] = useState(false);
  const url = attachmentUrl(server, session, conversationId, attachment.id);
  const headers = authHeaders(session);
  // An outgoing bubble is painted the brand colour and an incoming one is not,
  // so a control needs a fill that stands off whichever it sits on and a glyph
  // that stands off the fill. Taking both from one colour makes one of the two
  // invisible in some theme.
  const control = outgoing ? contrastOn(brand) : colors.ink;
  const onControl = outgoing ? brand : colors.surface;

  if (attachment.kind === "image") {
    return <ImageAttachment url={url} headers={headers} colors={colors} s={s} />;
  }
  if (attachment.kind === "audio") {
    return <AudioAttachment url={url} headers={headers} id={attachment.id} mime={attachment.mime} control={control} onControl={onControl} s={s} />;
  }
  return (
    <Pressable
      disabled={opening}
      onPress={async () => {
        if (opening) return;
        setOpening(true);
        try {
          if (!await Sharing.isAvailableAsync()) throw new Error(c.shareUnavailable);
          const extension = /\.([a-z0-9]{1,8})$/i.exec(attachment.filename || "")?.[1] || (attachment.kind === "video" ? "mp4" : "bin");
          const uri = await downloadAttachment(url, headers, attachment.id, extension);
          await Sharing.shareAsync(uri, { mimeType: attachment.mime, dialogTitle: attachment.filename || s.attachment.generic });
        } catch (error) { Alert.alert(c.attachmentFailed, error instanceof Error ? error.message : c.retry); }
        finally { setOpening(false); }
      }}
      style={({ pressed }) => [styles.file, pressed && styles.pressed]}
      accessibilityRole="button"
      accessibilityLabel={`${c.openFile}: ${attachment.filename || s.attachment.generic}`}
    >
      <View style={[styles.fileGlyph, { borderColor: control }]}>
        {opening ? <ActivityIndicator color={control} size="small" /> : <Ionicons name={attachment.kind === "video" ? "play" : "download-outline"} size={16} color={control} />}
      </View>
      <View style={styles.fileBody}>
        <Text style={[styles.fileName, { color: control }]} numberOfLines={1}>
          {attachment.filename || s.attachment.generic}
        </Text>
        {attachment.size_bytes ? (
          <Text style={[styles.fileSize, { color: control }]}>{humanSize(attachment.size_bytes)}</Text>
        ) : null}
      </View>
    </Pressable>
  );
}

function AudioAttachment({
  mime,
  url,
  headers,
  id,
  control,
  onControl,
  s,
}: {
  url: string;
  headers: Record<string, string>;
  id: string;
  mime: string;
  control: string;
  onControl: string;
  s: Strings;
}) {
  const base = mime.toLowerCase().split(";")[0].trim();
  const nativeCompatible = ["audio/mp4", "audio/m4a", "audio/x-m4a", "audio/mpeg", "audio/mp3", "audio/wav", "audio/x-wav", "audio/aac"].includes(base);
  const convert = Platform.OS === "ios" && !nativeCompatible;
  const extension = convert ? "m4a" : ({ "audio/ogg": "ogg", "audio/opus": "ogg", "video/ogg": "ogg", "audio/webm": "webm", "audio/mpeg": "mp3", "audio/mp3": "mp3", "audio/wav": "wav", "audio/x-wav": "wav", "audio/aac": "aac", "audio/flac": "flac" } as Record<string, string>)[base] || "m4a";
  const playbackUrl = convert ? `${url}?format=m4a` : url;
  const { path: localPath, failed, retry } = useCachedAudio(playbackUrl, headers, id, extension);
  const c = chatStrings();
  if (failed) return <Pressable onPress={retry} accessibilityRole="button" accessibilityLabel={c.attachmentRetry} style={{ padding: 10 }}><Text style={{ color: control }}>{c.audioFailed}</Text><Text style={{ color: control, fontWeight: "600", marginTop: 4 }}>{c.retry}</Text></Pressable>;
  if (!localPath) {
    return <Row control={control} onControl={onControl} busy playing={false} progress={0} label="0:00" />;
  }
  return <VoiceNote onRetry={retry} uri={localPath} control={control} onControl={onControl} s={s} />;
}

const styles = StyleSheet.create({
  image: { width: 230, height: 230, borderRadius: 12 },
  broken: { width: 230, height: 120, borderRadius: 12, alignItems: "center", justifyContent: "center" },
  brokenText: { fontSize: 13 },
  audio: { flexDirection: "row", alignItems: "center", gap: 10, minWidth: 200, paddingVertical: 2 },
  playButton: { width: 36, height: 36, borderRadius: 18, alignItems: "center", justifyContent: "center" },
  pressed: { opacity: 0.6 },
  audioBody: { flex: 1, justifyContent: "center" },
  track: { height: 3, borderRadius: 2 },
  trackFill: { position: "absolute", top: 0, left: 0, height: 3, borderRadius: 2 },
  audioTime: { fontSize: 12, marginTop: 7, opacity: 0.85 },
  file: { flexDirection: "row", alignItems: "center", gap: 10, minWidth: 180, paddingVertical: 2 },
  fileGlyph: {
    width: 32,
    height: 32,
    borderRadius: 8,
    borderWidth: 1,
    alignItems: "center",
    justifyContent: "center",
    opacity: 0.8,
  },
  fileBody: { flex: 1, minWidth: 0 },
  fileName: { fontSize: 14, fontWeight: Platform.OS === "ios" ? "600" : "500" },
  fileSize: { fontSize: 11, opacity: 0.7, marginTop: 1 },
});
