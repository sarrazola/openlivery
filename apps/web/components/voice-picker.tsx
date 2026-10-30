"use client";

import { useEffect, useRef, useState } from "react";
import { ExternalLink, LoaderCircle, Pause, Play } from "lucide-react";
import { AiHint } from "@/components/ai-hint";
import { Alert } from "@/components/ui";
import { api, messageFrom } from "@/lib/api";
import { useT } from "@/lib/i18n";
import type { PhoneVoice } from "@/types";

const LIBRARY = "https://elevenlabs.io/app/voice-library";

/** The agent's voice, chosen by its ID in the ElevenLabs voice library: the
 * operator finds and listens to voices there, pastes the one they like and
 * can hear it again here before saving. */
export function VoicePicker({ value, name, onChange }: { value: string; name: string; onChange: (voice: { id: string; name: string }) => void }) {
  const t = useT();
  const [pasted, setPasted] = useState("");
  const [voice, setVoice] = useState<PhoneVoice | null>(null);
  const [looking, setLooking] = useState(false);
  const [error, setError] = useState("");
  const [playing, setPlaying] = useState(false);
  const audio = useRef<HTMLAudioElement | null>(null);

  // The chosen voice, looked up for its accent and its sample.
  useEffect(() => {
    if (!value) { setVoice(null); return; }
    let alive = true;
    api<PhoneVoice>(`/phone/voices/${encodeURIComponent(value)}`)
      .then((found) => { if (alive) setVoice(found); })
      .catch(() => { if (alive) setVoice(null); });
    return () => { alive = false; };
  }, [value]);
  useEffect(() => () => audio.current?.pause(), []);

  async function use() {
    setLooking(true); setError("");
    try {
      const found = await api<PhoneVoice>(`/phone/voices/${encodeURIComponent(pasted.trim())}`);
      setVoice(found);
      onChange({ id: found.voice_id, name: found.name });
      setPasted("");
    } catch (err) { setError(messageFrom(err)); } finally { setLooking(false); }
  }

  function listen() {
    audio.current?.pause();
    if (playing || !voice?.preview_url) { setPlaying(false); return; }
    audio.current = new Audio(voice.preview_url);
    audio.current.onended = () => setPlaying(false);
    audio.current.play().catch(() => setPlaying(false));
    setPlaying(true);
  }

  return <div className="voice-picker">
    {value && <div className="voice-chosen">
      <button type="button" className="button ghost small" onClick={listen} disabled={!voice?.preview_url} aria-label={t("phone.channel.listen")}>{playing ? <Pause size={14} /> : <Play size={14} />}</button>
      <span><strong>{voice?.name || name || value}</strong><small>{[voice?.accent, voice?.gender].filter(Boolean).join(" · ") || value}</small></span>
    </div>}
    <div className="field-label-row"><span className="voice-id-label">{t("phone.channel.voiceIdLabel")} <AiHint text={t("phone.channel.voiceIdHelp")} /></span><a className="guide-link" href={LIBRARY} target="_blank" rel="noreferrer"><ExternalLink size={13} /> {t("phone.channel.voiceLibrary")}</a></div>
    <div className="voice-paste">
      <input value={pasted} placeholder={t("phone.channel.voiceIdPlaceholder")} aria-label={t("phone.channel.voiceIdLabel")} onChange={(event) => { setPasted(event.target.value); setError(""); }} />
      <button type="button" className="button secondary" disabled={looking || !pasted.trim()} onClick={use}>{looking ? <LoaderCircle className="spin" size={14} /> : t("phone.channel.useVoiceId")}</button>
    </div>
    {error && <Alert>{error}</Alert>}
  </div>;
}
