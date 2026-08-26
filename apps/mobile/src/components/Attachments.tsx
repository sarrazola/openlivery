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
  Linking,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { Image } from "expo-image";
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
  if (failed) {
    return (
      <View style={[styles.broken, { backgroundColor: colors.bubbleIn }]}>
        <Text style={[styles.brokenText, { color: colors.muted }]}>{s.attachment.imageUnavailable}</Text>
      </View>
    );
  }
  return (
    <Image
      source={{ uri: url, headers }}
      style={styles.image}
      contentFit="cover"
      transition={120}
      onError={() => setFailed(true)}
      accessibilityLabel={s.attachment.image}
    />
  );
}

/**
 * Fetch an attachment into the cache once and hand back its local path.
 *
 * The audio player asks for byte ranges as it goes, and those requests do not
 * carry the session, so streaming a credentialed URL stalls. Downloading first
 * sidesteps that and means replaying costs nothing.
 */
function useCachedAudio(url: string, headers: Record<string, string>, id: string): string | null {
  const [path, setPath] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const folder = new Directory(Paths.cache, "attachments");
        if (!folder.exists) folder.create({ intermediates: true });
        const target = new File(folder, `${id}.m4a`);
        if (!target.exists) {
          await File.downloadFileAsync(url, target, { headers, idempotent: true });
        }
        if (!cancelled) setPath(target.uri);
      } catch {
        // Leave it unplayable rather than throwing: the rest of the
        // conversation is still worth showing.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [url, id]);

  return path;
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
  uri,
  control,
  onControl,
  s,
}: {
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

  const playing = status.playing;
  const duration = status.duration || 0;
  const elapsed = status.currentTime || 0;
  const progress = duration > 0 ? Math.min(elapsed / duration, 1) : 0;

  return (
    <Row
      control={control}
      onControl={onControl}
      busy={status.isBuffering && !playing}
      playing={playing}
      progress={progress}
      label={clock(playing || elapsed > 0 ? elapsed : duration)}
      accessibilityLabel={playing ? s.attachment.pause : s.attachment.play}
      onPress={() => {
        if (playing) {
          player.pause();
          return;
        }
        // Replaying after it ended needs an explicit rewind.
        if (duration > 0 && elapsed >= duration - 0.15) player.seekTo(0);
        player.play();
      }}
    />
  );
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
    return <AudioAttachment url={url} headers={headers} id={attachment.id} control={control} onControl={onControl} s={s} />;
  }
  return (
    <Pressable
      onPress={() => Linking.openURL(url).catch(() => {})}
      style={({ pressed }) => [styles.file, pressed && styles.pressed]}
      accessibilityRole="button"
    >
      <View style={[styles.fileGlyph, { borderColor: control }]}>
        <Ionicons
          name={attachment.kind === "video" ? "play" : "download-outline"}
          size={16}
          color={control}
        />
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
  control: string;
  onControl: string;
  s: Strings;
}) {
  const localPath = useCachedAudio(url, headers, id);
  if (!localPath) {
    return <Row control={control} onControl={onControl} busy playing={false} progress={0} label="0:00" />;
  }
  return <VoiceNote uri={localPath} control={control} onControl={onControl} s={s} />;
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
