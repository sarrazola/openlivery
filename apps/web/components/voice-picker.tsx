"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { CheckCircle2, Circle, ExternalLink, LoaderCircle, Pause, Play } from "lucide-react";
import { AiHint } from "@/components/ai-hint";
import { Alert } from "@/components/ui";
import { api, messageFrom } from "@/lib/api";
import { voicePickerExtensions } from "@/lib/extensions/voice-picker";
import { useLanguage, useT } from "@/lib/i18n";
import type { PhoneVoice } from "@/types";

const LIBRARY = "https://elevenlabs.io/app/voice-library";

type VoicePickerProps = { language: string; value: string; name: string; onChange: (voice: { id: string; name: string }) => void };

/** The agent's voice. When the deployment offers a set of voices it is picked
 * from that list, and pasting an ID from the ElevenLabs library stays for any
 * other voice; otherwise the ID is the way to choose one. */
export function VoicePicker(props: VoicePickerProps) {
  return voicePickerExtensions.voices.length ? <CatalogVoicePicker {...props} /> : <LibraryVoicePicker {...props} />;
}

/** One sample at a time: playing another one stops the first. */
function useSample() {
  const audio = useRef<HTMLAudioElement | null>(null);
  const [playing, setPlaying] = useState("");
  useEffect(() => () => audio.current?.pause(), []);
  function toggle(key: string, url: string | null | undefined) {
    audio.current?.pause();
    if (playing === key || !url) { setPlaying(""); return; }
    const next = new Audio(url);
    next.onended = () => setPlaying("");
    next.play().catch(() => setPlaying(""));
    audio.current = next;
    setPlaying(key);
  }
  return { playing, toggle };
}

/** The ID of a voice in the ElevenLabs library, looked up before it is used.
 * `explain` writes out how to copy it instead of keeping that in a hint. */
function VoiceIdField({ onFound, explain = false }: { onFound: (voice: PhoneVoice) => void; explain?: boolean }) {
  const t = useT();
  const [pasted, setPasted] = useState("");
  const [looking, setLooking] = useState(false);
  const [error, setError] = useState("");

  async function use() {
    setLooking(true); setError("");
    try {
      onFound(await api<PhoneVoice>(`/phone/voices/${encodeURIComponent(pasted.trim())}`));
      setPasted("");
    } catch (err) { setError(messageFrom(err)); } finally { setLooking(false); }
  }

  return <>
    <div className="field-label-row"><span className="voice-id-label">{t("phone.channel.voiceIdLabel")} {!explain && <AiHint text={t("phone.channel.voiceIdHelp")} />}</span><a className="guide-link" href={LIBRARY} target="_blank" rel="noreferrer"><ExternalLink size={13} /> {t("phone.channel.voiceLibrary")}</a></div>
    <div className="voice-paste">
      <input value={pasted} placeholder={t("phone.channel.voiceIdPlaceholder")} aria-label={t("phone.channel.voiceIdLabel")} onChange={(event) => { setPasted(event.target.value); setError(""); }} />
      <button type="button" className="button secondary" disabled={looking || !pasted.trim()} onClick={use}>{looking ? <LoaderCircle className="spin" size={14} /> : t("phone.channel.useVoiceId")}</button>
    </div>
    {explain && <p className="field-help voice-id-steps">{t("phone.channel.voiceIdHelp")}</p>}
    {error && <Alert>{error}</Alert>}
  </>;
}

/** A voice chosen by its ID, with its accent and its sample. */
function ChosenVoice({ voice, fallback, isDefault }: { voice: PhoneVoice | null; fallback: string; isDefault: boolean }) {
  const t = useT();
  const { playing, toggle } = useSample();
  return <div className="voice-chosen">
    <button type="button" className="button ghost small" onClick={() => toggle("chosen", voice?.preview_url)} disabled={!voice?.preview_url} aria-label={t("phone.channel.listen")}>{playing ? <Pause size={14} /> : <Play size={14} />}</button>
    <span><strong>{voice?.name || fallback}</strong><small>{[voice?.accent, voice?.gender].filter(Boolean).join(" · ") || fallback}</small></span>
    {isDefault && <span className="pill">{t("phone.channel.defaultVoice")}</span>}
  </div>;
}

/** The voice chosen by its ID in the ElevenLabs voice library: the operator
 * finds and listens to voices there, pastes the one they like and can hear it
 * again here before saving. Without one, the agent speaks with the default
 * voice of its language, shown here so it is no surprise. */
function LibraryVoicePicker({ language, value, name, onChange }: VoicePickerProps) {
  const t = useT();
  const [voice, setVoice] = useState<PhoneVoice | null>(null);

  // The chosen voice (or the default one), looked up for its accent and its sample.
  useEffect(() => {
    let alive = true;
    api<PhoneVoice>(value ? `/phone/voices/${encodeURIComponent(value)}` : `/phone/default-voice?language=${encodeURIComponent(language)}`)
      .then((found) => { if (alive) setVoice(found); })
      .catch(() => { if (alive) setVoice(null); });
    return () => { alive = false; };
  }, [value, language]);

  return <div className="voice-picker">
    {(value || voice) && <ChosenVoice voice={voice} fallback={name || value} isDefault={!value} />}
    {value ? <button type="button" className="text-button align-start" onClick={() => onChange({ id: "", name: "" })}>{t("phone.channel.useDefaultVoice")}</button>
      : <p className="field-help">{t("phone.channel.defaultVoiceHint")}</p>}
    <VoiceIdField onFound={(found) => { setVoice(found); onChange({ id: found.voice_id, name: found.name }); }} />
  </div>;
}

/** The deployment's voices, one language at a time, each with its accent and
 * a sample that plays without asking the voice provider. A voice outside the
 * list is still chosen by its ID, behind a link under it. */
function CatalogVoicePicker({ language, value, name, onChange }: VoicePickerProps) {
  const { t, lang } = useLanguage();
  const voices = voicePickerExtensions.voices;
  const languages = useMemo(() => [...new Set(voices.map((voice) => voice.language))], [voices]);
  const listed = voices.some((voice) => voice.id === value);
  const fallback = voices.find((voice) => voice.default && voice.language === language);
  const selected = value || fallback?.id || "";
  const [shown, setShown] = useState(() => voices.find((voice) => voice.id === value)?.language || (languages.includes(language) ? language : languages[0]));
  const [other, setOther] = useState(false);
  const [custom, setCustom] = useState<PhoneVoice | null>(null);
  const { playing, toggle } = useSample();
  const options = useRef<HTMLDivElement | null>(null);
  const names = useMemo(() => ({
    language: new Intl.DisplayNames([lang], { type: "language" }),
    region: new Intl.DisplayNames([lang], { type: "region" }),
  }), [lang]);
  const languageName = (code: string) => { const named = names.language.of(code) || code; return named.charAt(0).toLocaleUpperCase(lang) + named.slice(1); };
  const shownVoices = voices.filter((voice) => voice.language === shown);

  // A voice pasted by its ID is not in the list: looked up for its name and sample.
  useEffect(() => {
    if (!value || listed) { setCustom(null); return; }
    if (custom?.voice_id === value) return;
    let alive = true;
    api<PhoneVoice>(`/phone/voices/${encodeURIComponent(value)}`)
      .then((found) => { if (alive) setCustom(found); })
      .catch(() => { if (alive) setCustom(null); });
    return () => { alive = false; };
  }, [value, listed]);

  // The chosen voice may sit far down the list: bring it into view.
  useEffect(() => {
    const box = options.current;
    const row = box?.querySelector<HTMLElement>(".voice-option.selected");
    if (box && row) box.scrollTop = Math.max(0, row.offsetTop - 8);
  }, [shown]);

  // Picking the default voice of the agent's language is the agent having none.
  function pick(id: string, voiceName: string) {
    onChange(id === fallback?.id ? { id: "", name: "" } : { id, name: voiceName });
  }

  return <div className="voice-picker">
    {value && !listed && <ChosenVoice voice={custom} fallback={name || value} isDefault={false} />}
    <div className="voice-toolbar">
      <span>{t("phone.channel.voiceCount", { count: shownVoices.length })}</span>
      {languages.length > 1 && <select value={shown} aria-label={t("phone.channel.voiceLanguage")} onChange={(event) => setShown(event.target.value)}>
        {languages.map((code) => <option key={code} value={code}>{languageName(code)}</option>)}
      </select>}
    </div>
    <div className="voice-options" ref={options} role="radiogroup" aria-label={t("phone.channel.voiceTitle")}>
      {shownVoices.map((voice) => {
        const chosen = voice.id === selected;
        return <div key={voice.id} className={`voice-option${chosen ? " selected" : ""}`}>
          <button type="button" className="voice-play" onClick={() => toggle(voice.id, voice.sample)} aria-label={`${t("phone.channel.listen")}: ${voice.name}`}>{playing === voice.id ? <Pause size={14} /> : <Play size={14} />}</button>
          <button type="button" role="radio" aria-checked={chosen} className="voice-pick" onClick={() => pick(voice.id, voice.name)}>
            <span className="voice-name"><strong>{voice.name}</strong><small>{[t(voice.gender === "female" ? "phone.channel.voiceFemale" : "phone.channel.voiceMale"), voice.place].filter(Boolean).join(" · ")}</small></span>
            {voice.id === fallback?.id && <span className="pill">{t("phone.channel.defaultVoice")}</span>}
            <span className="voice-tag">{languageName(voice.language)} · {names.region.of(voice.region) || voice.region}</span>
            {chosen ? <CheckCircle2 className="voice-check" size={18} /> : <Circle className="voice-check" size={18} />}
          </button>
        </div>;
      })}
    </div>
    {other ? <VoiceIdField explain onFound={(found) => { setCustom(found); onChange({ id: found.voice_id, name: found.name }); setOther(false); }} />
      : <p className="voice-other">{t("phone.channel.otherVoice")} <button type="button" className="text-button" onClick={() => setOther(true)}>{t("phone.channel.otherVoiceLink")}</button></p>}
  </div>;
}
