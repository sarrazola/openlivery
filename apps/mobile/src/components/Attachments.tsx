/**
 * Rendering what came in with a message.
 *
 * Attachments live behind the portal session, so none of them can be a plain
 * URL in a src: every fetch carries the bearer token. Images render inline,
 * voice notes get a play button and a running time, and anything else falls
 * back to a row you can tap to open.
 */

import { useEffect, useState } from "react";
import {
  ActivityIndicator,
  Linking,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { Image } from "expo-image";
import { Directory, File, Paths } from "expo-file-system";
import { useAudioPlayer, useAudioPlayerStatus } from "expo-audio";
import { attachmentUrl, authHeaders, type Attachment, type Session } from "../api";
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

function ImageAttachment({ url, headers, colors }: { url: string; headers: Record<string, string>; colors: Colors }) {
  const [failed, setFailed] = useState(false);
  if (failed) {
    return (
      <View style={[styles.broken, { backgroundColor: colors.bubbleIn }]}>
        <Text style={[styles.brokenText, { color: colors.muted }]}>Image unavailable</Text>
      </View>
    );
  }
  return (
    <Image
      source={{ uri: url, headers }}
      style={[styles.image, { backgroundColor: colors.bubbleIn }]}
      contentFit="cover"
      transition={120}
      onError={() => setFailed(true)}
      accessibilityLabel="Attached image"
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

function AudioAttachment({
  url,
  headers,
  id,
  seconds,
  control,
  onControl,
  colors,
}: {
  url: string;
  headers: Record<string, string>;
  id: string;
  seconds: number;
  /** The filled button and the played part of the track. */
  control: string;
  /** The glyph drawn on top of `control`. */
  onControl: string;
  colors: Colors;
}) {
  const localPath = useCachedAudio(url, headers, id);
  const player = useAudioPlayer(localPath ? { uri: localPath } : null);
  const status = useAudioPlayerStatus(player);
  const playing = status.playing;
  const loading = !localPath;
  const duration = status.duration || seconds || 0;
  const elapsed = status.currentTime || 0;
  const progress = duration > 0 ? Math.min(elapsed / duration, 1) : 0;

  return (
    <View style={styles.audio}>
      <Pressable
        onPress={() => {
          if (!localPath) return;
          if (playing) {
            player.pause();
          } else {
            // Replaying after it ended needs an explicit rewind.
            if (duration > 0 && elapsed >= duration - 0.15) player.seekTo(0);
            player.play();
          }
        }}
        hitSlop={8}
        style={({ pressed }) => [styles.playButton, { backgroundColor: control }, pressed && styles.pressed]}
        accessibilityRole="button"
        accessibilityLabel={playing ? "Pause voice note" : "Play voice note"}
      >
        {loading || (status.isBuffering && !playing) ? (
          <ActivityIndicator size="small" color={onControl} />
        ) : (
          <Text style={[styles.playGlyph, { color: onControl }]}>{playing ? "❚❚" : "▶"}</Text>
        )}
      </Pressable>
      <View style={styles.audioBody}>
        <View style={styles.track}>
          <View style={[styles.trackFill, { width: `${progress * 100}%`, backgroundColor: control }]} />
        </View>
        <Text style={[styles.audioTime, { color: control }]}>{clock(playing || elapsed > 0 ? elapsed : duration)}</Text>
      </View>
    </View>
  );
}

export function AttachmentView({ attachment, server, session, conversationId, outgoing, brand }: Props) {
  const colors = useColors();
  const url = attachmentUrl(server, session, conversationId, attachment.id);
  const headers = authHeaders(session);
  // An outgoing bubble is painted the brand colour and an incoming one is not,
  // so a control needs a fill that stands off whichever it sits on and a glyph
  // that stands off the fill. Taking both from one colour makes one of the two
  // invisible in some theme.
  const control = outgoing ? contrastOn(brand) : colors.ink;
  const onControl = outgoing ? brand : colors.surface;

  if (attachment.kind === "image") {
    return <ImageAttachment url={url} headers={headers} colors={colors} />;
  }
  if (attachment.kind === "audio") {
    return (
      <AudioAttachment
        url={url}
        headers={headers}
        id={attachment.id}
        seconds={0}
        control={control}
        onControl={onControl}
        colors={colors}
      />
    );
  }
  return (
    <Pressable
      onPress={() => Linking.openURL(url).catch(() => {})}
      style={({ pressed }) => [styles.file, pressed && styles.pressed]}
      accessibilityRole="button"
    >
      <View style={[styles.fileGlyph, { borderColor: control }]}>
        <Text style={[styles.fileGlyphText, { color: control }]}>
          {attachment.kind === "video" ? "▶" : "↓"}
        </Text>
      </View>
      <View style={styles.fileBody}>
        <Text style={[styles.fileName, { color: control }]} numberOfLines={1}>
          {attachment.filename || "Attachment"}
        </Text>
        {attachment.size_bytes ? (
          <Text style={[styles.fileSize, { color: control }]}>{humanSize(attachment.size_bytes)}</Text>
        ) : null}
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  image: { width: 220, height: 220, borderRadius: 12 },
  broken: { width: 220, height: 120, borderRadius: 12, alignItems: "center", justifyContent: "center" },
  brokenText: { fontSize: 13 },
  audio: { flexDirection: "row", alignItems: "center", gap: 10, minWidth: 190, paddingVertical: 2 },
  playButton: { width: 34, height: 34, borderRadius: 17, alignItems: "center", justifyContent: "center" },
  playGlyph: { fontSize: 13, lineHeight: 16, marginLeft: 1 },
  pressed: { opacity: 0.6 },
  audioBody: { flex: 1, gap: 5 },
  track: { height: 3, borderRadius: 2, backgroundColor: "rgba(127,127,127,0.35)", overflow: "hidden" },
  trackFill: { height: 3, borderRadius: 2 },
  audioTime: { fontSize: 11, opacity: 0.75 },
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
  fileGlyphText: { fontSize: 13 },
  fileBody: { flex: 1, minWidth: 0 },
  fileName: { fontSize: 14, fontWeight: Platform.OS === "ios" ? "600" : "500" },
  fileSize: { fontSize: 11, opacity: 0.7, marginTop: 1 },
});
