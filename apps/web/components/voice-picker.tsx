"use client";

import { useEffect, useRef, useState } from "react";
import { LoaderCircle, Pause, Play } from "lucide-react";
import Link from "next/link";
import { api } from "@/lib/api";
import { useLanguage } from "@/lib/i18n";
import type { PhoneVoice } from "@/types";

/** Voices from the ElevenLabs library in the interface's language, with a
 * preview to listen to before choosing. Needs the agency's ElevenLabs key. */
export function VoicePicker({ language, value, name, onChange }: { language: string; value: string; name: string; onChange: (voice: { id: string; name: string }) => void }) {
  const { t } = useLanguage();
  const [search, setSearch] = useState("");
  const [voices, setVoices] = useState<PhoneVoice[] | null>(null);
  const [playing, setPlaying] = useState<string | null>(null);
  const [unavailable, setUnavailable] = useState(false);
  const audio = useRef<HTMLAudioElement | null>(null);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      api<PhoneVoice[]>(`/phone/voices?language=${encodeURIComponent(language)}&search=${encodeURIComponent(search.trim())}`)
        .then((found) => { setVoices(found); setUnavailable(false); })
        .catch(() => { setVoices([]); setUnavailable(true); });
    }, search ? 350 : 0);
    return () => window.clearTimeout(timer);
  }, [language, search]);
  useEffect(() => () => audio.current?.pause(), []);

  function listen(voice: PhoneVoice) {
    audio.current?.pause();
    if (playing === voice.voice_id || !voice.preview_url) { setPlaying(null); return; }
    audio.current = new Audio(voice.preview_url);
    audio.current.onended = () => setPlaying(null);
    audio.current.play().catch(() => setPlaying(null));
    setPlaying(voice.voice_id);
  }

  return <div className="voice-picker">
    {value && <p className="social-meta">{t("phone.channel.chosen")}: <strong>{name || value}</strong></p>}
    {!unavailable && <input type="search" className="voice-search" value={search} aria-label={t("phone.channel.searchVoices")} placeholder={t("phone.channel.searchVoices")} onChange={(event) => setSearch(event.target.value)} />}
    {unavailable ? <p className="social-meta">{t("phone.agent.needsElevenLabs")} <Link href="/settings/phone">{t("phone.channel.goToSettings")}</Link></p>
      : voices === null ? <p className="field-help"><LoaderCircle className="spin" size={14} /></p>
      : !voices.length ? <p className="social-meta">{t("phone.channel.noVoices")}</p>
      : <ul className="voice-list">{voices.map((voice) => <li key={voice.voice_id} className={voice.voice_id === value ? "chosen" : ""}>
        <button type="button" className="button ghost small" onClick={() => listen(voice)} disabled={!voice.preview_url} aria-label={t("phone.channel.listen")}>{playing === voice.voice_id ? <Pause size={14} /> : <Play size={14} />}</button>
        <span><strong>{voice.name}</strong><small>{[voice.accent, voice.gender].filter(Boolean).join(" · ")}</small></span>
        <button type="button" className={`button small ${voice.voice_id === value ? "primary" : "secondary"}`} onClick={() => onChange({ id: voice.voice_id, name: voice.name })}>{voice.voice_id === value ? t("phone.channel.chosen") : t("phone.channel.choose")}</button>
      </li>)}</ul>}
  </div>;
}
