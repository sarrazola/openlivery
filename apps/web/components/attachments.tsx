"use client";

import { DragEvent, MouseEvent, ReactNode, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { ChevronLeft, ChevronRight, FileText, Mic, Paperclip, Pause, Play, Square, X } from "lucide-react";
import { useT } from "@/lib/i18n";
import type { Attachment } from "@/types";

/** One image of a conversation-wide gallery the lightbox can navigate. */
export type GalleryImage = { id: string; url: string; name: string | null };

function formatClock(value: number): string {
  if (!isFinite(value) || value < 0) return "0:00";
  const total = Math.round(value);
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}

const WAVE_BARS = 40;
const PLAYBACK_RATES = [1, 1.5, 2];

/** Deterministic pseudo-waveform for audio the browser cannot decode (e.g.
 * ogg/opus on Safari): stable bars derived from the source URL. */
function fallbackWave(seed: string): number[] {
  let hash = 2166136261;
  for (let i = 0; i < seed.length; i++) {
    hash = Math.imul(hash ^ seed.charCodeAt(i), 16777619);
  }
  return Array.from({ length: WAVE_BARS }, (_, index) => {
    hash = Math.imul(hash ^ (index + 1), 16777619);
    return 0.25 + (Math.abs(hash) % 1000) / 1400;
  });
}

/** Custom voice-note player, WhatsApp-style: real waveform bars that fill
 * smoothly as the audio plays, click-to-seek, and a 1x/1.5x/2x speed toggle. */
export function AudioBubble({ src, stamp }: { src: string; stamp?: string }) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const [playing, setPlaying] = useState(false);
  const [time, setTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [rate, setRate] = useState(1);
  const [bars, setBars] = useState<number[] | null>(null);

  // Build the waveform by decoding the audio (Web Audio API); fall back to a
  // stable pseudo-wave when the browser cannot decode the codec.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const response = await fetch(src, { credentials: "include" });
        const buffer = await response.arrayBuffer();
        const Ctx = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
        const context = new Ctx();
        const decoded = await context.decodeAudioData(buffer);
        const channel = decoded.getChannelData(0);
        const block = Math.max(1, Math.floor(channel.length / WAVE_BARS));
        const peaks = Array.from({ length: WAVE_BARS }, (_, index) => {
          let sum = 0;
          let count = 0;
          for (let offset = 0; offset < block; offset += 32) {
            sum += Math.abs(channel[index * block + offset] || 0);
            count++;
          }
          return count ? sum / count : 0;
        });
        const max = Math.max(...peaks, 0.001);
        if (!cancelled) setBars(peaks.map((peak) => Math.max(0.18, peak / max)));
        void context.close();
      } catch {
        if (!cancelled) setBars(fallbackWave(src));
      }
    })();
    return () => { cancelled = true; };
  }, [src]);

  // Smooth progress while playing (timeupdate alone fires ~4x/s and looks jumpy).
  useEffect(() => {
    if (!playing) return;
    let frame: number;
    const tick = () => {
      setTime(audioRef.current?.currentTime || 0);
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [playing]);

  function onLoadedMetadata() {
    const audio = audioRef.current;
    if (!audio) return;
    if (isFinite(audio.duration)) {
      setDuration(audio.duration);
      return;
    }
    // MediaRecorder blobs report Infinity until forced to the end once.
    const restore = () => {
      audio.currentTime = 0;
      setDuration(isFinite(audio.duration) ? audio.duration : 0);
      audio.removeEventListener("timeupdate", restore);
    };
    audio.addEventListener("timeupdate", restore);
    audio.currentTime = 1e7;
  }

  function toggle() {
    const audio = audioRef.current;
    if (!audio) return;
    if (playing) audio.pause();
    else void audio.play();
  }

  function cycleRate() {
    const next = PLAYBACK_RATES[(PLAYBACK_RATES.indexOf(rate) + 1) % PLAYBACK_RATES.length];
    setRate(next);
    if (audioRef.current) audioRef.current.playbackRate = next;
  }

  function seek(event: MouseEvent<HTMLDivElement>) {
    const audio = audioRef.current;
    if (!audio || !duration) return;
    const rect = event.currentTarget.getBoundingClientRect();
    const fraction = Math.min(Math.max((event.clientX - rect.left) / rect.width, 0), 1);
    audio.currentTime = fraction * duration;
    setTime(fraction * duration);
  }

  const wave = bars || fallbackWave(src);
  const progress = duration ? Math.min(time / duration, 1) : 0;
  const filled = progress * wave.length;
  return (
    <div className="audio-bubble">
      <button type="button" className="audio-play" onClick={toggle} aria-label={playing ? "Pause" : "Play"}>
        {playing ? <Pause size={15} /> : <Play size={15} />}
      </button>
      <div className="audio-main">
        <div className="audio-wave" onClick={seek} role="progressbar" aria-valuenow={Math.round(progress * 100)} aria-valuemin={0} aria-valuemax={100}>
          {wave.map((peak, index) => (
            <i
              key={index}
              className={index < filled ? "filled" : ""}
              style={{ height: `${Math.round(4 + peak * 20)}px` }}
            />
          ))}
        </div>
        <div className="audio-meta">
          <span>{formatClock(playing || time > 0 ? time : duration)}</span>
          <span>{stamp ?? formatClock(duration)}</span>
        </div>
      </div>
      <button type="button" className="audio-rate" onClick={cycleRate} aria-label={`Playback speed ${rate}x`}>
        {rate}×
      </button>
      <audio
        ref={audioRef}
        src={src}
        preload="metadata"
        onLoadedMetadata={onLoadedMetadata}
        onDurationChange={onLoadedMetadata}
        onTimeUpdate={() => { if (!playing) setTime(audioRef.current?.currentTime || 0); }}
        onPlay={() => { setPlaying(true); if (audioRef.current) audioRef.current.playbackRate = rate; }}
        onPause={() => setPlaying(false)}
        onEnded={() => { setPlaying(false); setTime(0); }}
      />
    </div>
  );
}

/** Full-screen in-app preview with prev/next navigation over every image of
 * the conversation (arrow keys work too), like WhatsApp/CRM chats. */
export function Lightbox({ items, index, onIndex, onClose }: {
  items: GalleryImage[];
  index: number;
  onIndex: (index: number) => void;
  onClose: () => void;
}) {
  const t = useT();
  const count = items.length;
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
      if (count > 1 && event.key === "ArrowLeft") onIndex((index - 1 + count) % count);
      if (count > 1 && event.key === "ArrowRight") onIndex((index + 1) % count);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose, onIndex, index, count]);
  const item = items[index];
  if (!item) return null;
  return createPortal(
    <div className="lightbox" role="dialog" aria-modal="true" onClick={onClose}>
      <button type="button" className="lightbox-close" aria-label={t("chat.closePreview")} onClick={onClose}><X size={22} /></button>
      {count > 1 && (
        <button type="button" className="lightbox-nav prev" aria-label="Previous" onClick={(event) => { event.stopPropagation(); onIndex((index - 1 + count) % count); }}>
          <ChevronLeft size={26} />
        </button>
      )}
      <figure onClick={(event) => event.stopPropagation()}>
        <img src={item.url} alt={item.name || "attachment"} />
        <figcaption>{item.name || ""}{count > 1 ? `${item.name ? " · " : ""}${index + 1}/${count}` : ""}</figcaption>
      </figure>
      {count > 1 && (
        <button type="button" className="lightbox-nav next" aria-label="Next" onClick={(event) => { event.stopPropagation(); onIndex((index + 1) % count); }}>
          <ChevronRight size={26} />
        </button>
      )}
    </div>,
    document.body,
  );
}

/** Renders a message's attachments as chat media: inline images (multiple ones
 * collapse into a WhatsApp-style grid; clicking opens the lightbox, navigable
 * across every image in the chat when `gallery` is provided), a voice-note
 * player, inline video, and a download chip for files. */
export function MessageAttachments({ attachments, urlFor, gallery, stamp }: {
  attachments?: Attachment[];
  urlFor: (attachment: Attachment) => string;
  gallery?: GalleryImage[];
  /** Clock time of the message, shown inside the voice-note player (WhatsApp-style). */
  stamp?: string;
}) {
  const [previewIndex, setPreviewIndex] = useState<number | null>(null);
  if (!attachments?.length) return null;

  const images = attachments.filter((attachment) => attachment.kind === "image");
  const others = attachments.filter((attachment) => attachment.kind !== "image");
  const items: GalleryImage[] = gallery?.length
    ? gallery
    : images.map((attachment) => ({ id: attachment.id, url: urlFor(attachment), name: attachment.filename }));

  function openImage(attachment: Attachment) {
    const index = items.findIndex((item) => item.id === attachment.id);
    setPreviewIndex(index >= 0 ? index : 0);
  }

  const gridImages = images.slice(0, 4);
  const extra = images.length - gridImages.length;
  return (
    <div className="attachments">
      {images.length > 1 ? (
        <div className={`attachment-grid count-${gridImages.length}`}>
          {gridImages.map((attachment, index) => (
            <button key={attachment.id} type="button" className="attachment-tile" onClick={() => openImage(attachment)}>
              <img src={urlFor(attachment)} alt={attachment.filename || "attachment"} loading="lazy" />
              {extra > 0 && index === gridImages.length - 1 && <span className="attachment-more">+{extra}</span>}
            </button>
          ))}
        </div>
      ) : (
        images.map((attachment) => (
          <button key={attachment.id} type="button" className="attachment-image" onClick={() => openImage(attachment)}>
            <img src={urlFor(attachment)} alt={attachment.filename || "attachment"} loading="lazy" />
          </button>
        ))
      )}
      {others.map((attachment) => {
        const url = urlFor(attachment);
        if (attachment.kind === "audio") {
          return <AudioBubble key={attachment.id} src={url} stamp={stamp} />;
        }
        // Also match older rows stored before "video" was a first-class kind.
        if (attachment.kind === "video" || attachment.mime.startsWith("video/")) {
          return <video key={attachment.id} className="attachment-video" controls preload="metadata" src={url} />;
        }
        return (
          <a key={attachment.id} className="attachment-file" href={url} target="_blank" rel="noreferrer">
            <FileText size={15} /> <span>{attachment.filename || "file"}</span>
          </a>
        );
      })}
      {previewIndex !== null && (
        <Lightbox items={items} index={previewIndex} onIndex={setPreviewIndex} onClose={() => setPreviewIndex(null)} />
      )}
    </div>
  );
}

/** Attachment staged in the composer, WhatsApp-style: a preview with the file's
 * name and a cancel button; nothing is sent until the user presses send. */
export function PendingAttachment({ file, onCancel }: { file: File; onCancel: () => void }) {
  const t = useT();
  const [url, setUrl] = useState("");
  useEffect(() => {
    const objectUrl = URL.createObjectURL(file);
    setUrl(objectUrl);
    return () => URL.revokeObjectURL(objectUrl);
  }, [file]);
  const size = file.size >= 1024 * 1024
    ? `${(file.size / (1024 * 1024)).toFixed(1)} MB`
    : `${Math.max(1, Math.round(file.size / 1024))} KB`;
  return (
    <div className="pending-attachment">
      {file.type.startsWith("image/") && url ? <img src={url} alt={file.name} />
        : file.type.startsWith("video/") && url ? <video src={url} muted />
        : <span className="pending-icon">{file.type.startsWith("audio/") ? <Mic size={17} /> : <FileText size={17} />}</span>}
      <div className="pending-meta"><strong>{file.name}</strong><small>{size} · {t("chat.pendingHint")}</small></div>
      <button type="button" onClick={onCancel} aria-label={t("chat.removeAttachment")} title={t("chat.removeAttachment")}><X size={16} /></button>
    </div>
  );
}

/** Paperclip button + hidden file input for chat composers. */
export function AttachButton({ onFile, disabled, title, accept }: { onFile: (file: File) => void; disabled?: boolean; title: string; accept?: string }) {
  const inputRef = useRef<HTMLInputElement>(null);
  return (
    <>
      <button type="button" className="composer-attach" disabled={disabled} title={title} aria-label={title} onClick={() => inputRef.current?.click()}>
        <Paperclip size={18} />
      </button>
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        hidden
        onChange={(event) => {
          const file = event.target.files?.[0];
          if (file) onFile(file);
          event.currentTarget.value = "";
        }}
      />
    </>
  );
}

const RECORD_MIMES = ["audio/mp4", "audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus"];

function recordingExtension(mime: string): string {
  if (mime.includes("mp4")) return "m4a";
  if (mime.includes("ogg")) return "ogg";
  if (mime.includes("mpeg")) return "mp3";
  return "webm";
}

/** Microphone button for chat composers: records a voice note with the browser's
 * MediaRecorder and hands the finished file to `onRecorded`. */
export function RecordButton({ onRecorded, onError, disabled, title, titleStop }: {
  onRecorded: (file: File) => void;
  onError?: () => void;
  disabled?: boolean;
  title: string;
  titleStop: string;
}) {
  const [recording, setRecording] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => () => {
    // Unmount while recording: stop the recorder and release the microphone.
    if (timerRef.current) clearInterval(timerRef.current);
    const recorder = recorderRef.current;
    if (recorder) {
      recorder.onstop = () => recorder.stream.getTracks().forEach((track) => track.stop());
      if (recorder.state !== "inactive") recorder.stop();
    }
  }, []);

  async function start() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mime = RECORD_MIMES.find((item) => typeof MediaRecorder !== "undefined" && MediaRecorder.isTypeSupported(item));
      const recorder = mime ? new MediaRecorder(stream, { mimeType: mime }) : new MediaRecorder(stream);
      chunksRef.current = [];
      recorder.ondataavailable = (event) => { if (event.data.size) chunksRef.current.push(event.data); };
      recorder.onstop = () => {
        stream.getTracks().forEach((track) => track.stop());
        const type = (recorder.mimeType || "audio/webm").split(";")[0];
        const blob = new Blob(chunksRef.current, { type });
        if (blob.size) onRecorded(new File([blob], `voice-note.${recordingExtension(type)}`, { type }));
      };
      recorderRef.current = recorder;
      recorder.start();
      setRecording(true);
      setSeconds(0);
      timerRef.current = setInterval(() => setSeconds((value) => value + 1), 1000);
    } catch {
      onError?.();
    }
  }

  function stop() {
    if (timerRef.current) clearInterval(timerRef.current);
    timerRef.current = null;
    recorderRef.current?.stop();
    recorderRef.current = null;
    setRecording(false);
  }

  const elapsed = `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
  return (
    <button
      type="button"
      className={`composer-attach record${recording ? " recording" : ""}`}
      disabled={disabled}
      title={recording ? titleStop : title}
      aria-label={recording ? titleStop : title}
      onClick={recording ? stop : start}
    >
      {recording ? <><Square size={14} /><span className="record-time">{elapsed}</span></> : <Mic size={18} />}
    </button>
  );
}

/** Drag-and-drop file target: spread `dropProps` on a container, add the
 * `drop-target` positioning class to it, and render `overlay` inside it. */
export function useFileDrop(onFile: (file: File) => void, { enabled = true, label }: { enabled?: boolean; label: string }) {
  const [dragging, setDragging] = useState(false);
  const depth = useRef(0);

  function onDragEnter(event: DragEvent) {
    if (!enabled || !event.dataTransfer?.types.includes("Files")) return;
    event.preventDefault();
    depth.current += 1;
    setDragging(true);
  }
  function onDragOver(event: DragEvent) {
    if (!enabled || !event.dataTransfer?.types.includes("Files")) return;
    event.preventDefault();
  }
  function onDragLeave(event: DragEvent) {
    if (!enabled) return;
    event.preventDefault();
    depth.current = Math.max(0, depth.current - 1);
    if (depth.current === 0) setDragging(false);
  }
  function onDrop(event: DragEvent) {
    if (!enabled) return;
    event.preventDefault();
    depth.current = 0;
    setDragging(false);
    const file = event.dataTransfer?.files?.[0];
    if (file) onFile(file);
  }

  const overlay: ReactNode = dragging ? <div className="drop-overlay">{label}</div> : null;
  return { dropProps: { onDragEnter, onDragOver, onDragLeave, onDrop }, overlay };
}
