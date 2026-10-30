"use client";

import { useEffect, useRef, useState } from "react";
import { LoaderCircle, Pause, Play } from "lucide-react";
import Link from "next/link";
import { Alert } from "@/components/ui";
import { api, messageFrom } from "@/lib/api";
import { useLanguage } from "@/lib/i18n";
import type { PhoneVoice } from "@/types";

/** Voices from the ElevenLabs library in the interface's language, with a
 * preview to listen to before choosing, or one pasted by its ID from that
 * library. Needs the agency's ElevenLabs key. */
export function VoicePicker({ language, value, name, onChange }: { language: string; value: string; name: string; onChange: (voice: { id: string; name: string }) => void }) {
  const { t } = useLanguage();
  const [search, setSearch] = useState("");
  const [voices, setVoices] = useState<PhoneVoice[] | null>(null);
  const [playing, setPlaying] = useState<string | null>(null);
  const [unavailable, setUnavailable] = useState(false);
  const [pasted, setPasted] = useState("");
  const [looking, setLooking] = useState(false);
  const [pasteError, setPasteError] = useState("");
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

  async function usePasted() {
    setLooking(true); setPasteError("");
    try {
      const voice = await api<PhoneVoice>(`/phone/voices/${encodeURIComponent(pasted.trim())}`);
      onChange({ id: voice.voice_id, name: voice.name });
      setPasted("");
    } catch (err) { setPasteError(messageFrom(err)); } finally { setLooking(false); }
  }

  return <div className="voice-picker">
    {value && <p className="social-meta">{t("phone.channel.chosen")}: <strong>{name || value}</strong></p>}
    {!unavailable && <input type="search" className="voice-search" value={search} aria-label={t("phone.channel.searchVoices")} placeholder={t("phone.channel.searchVoices")} onChange={(event) => setSearch(event.target.value)} />}
    {unavailable ? <p className="social-meta">{t("phone.agent.needsElevenLabs")} <Link href="/settings/providers">{t("phone.channel.goToSettings")}</Link></p>
      : voices === null ? <p className="field-help"><LoaderCircle className="spin" size={14} /></p>
      : !voices.length ? <p className="social-meta">{t("phone.channel.noVoices")}</p>
      : <ul className="voice-list">{voices.map((voice) => <li key={voice.voice_id} className={voice.voice_id === value ? "chosen" : ""}>
        <button type="button" className="button ghost small" onClick={() => listen(voice)} disabled={!voice.preview_url} aria-label={t("phone.channel.listen")}>{playing === voice.voice_id ? <Pause size={14} /> : <Play size={14} />}</button>
        <span><strong>{voice.name}</strong><small>{[voice.accent, voice.gender].filter(Boolean).join(" · ")}</small></span>
        <button type="button" className={`button small ${voice.voice_id === value ? "primary" : "secondary"}`} onClick={() => onChange({ id: voice.voice_id, name: voice.name })}>{voice.voice_id === value ? t("phone.channel.chosen") : t("phone.channel.choose")}</button>
      </li>)}</ul>}
    {!unavailable && <div className="voice-paste">
      <input value={pasted} placeholder={t("phone.channel.pasteVoiceId")} aria-label={t("phone.channel.pasteVoiceId")} onChange={(event) => { setPasted(event.target.value); setPasteError(""); }} />
      <button type="button" className="button secondary" disabled={looking || !pasted.trim()} onClick={usePasted}>{looking ? <LoaderCircle className="spin" size={14} /> : t("phone.channel.useVoiceId")}</button>
    </div>}
    {pasteError && <Alert>{pasteError}</Alert>}
  </div>;
}
