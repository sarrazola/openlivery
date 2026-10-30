"use client";

import { useState } from "react";
import { LoaderCircle, Save } from "lucide-react";
import { VoicePicker } from "@/components/voice-picker";
import { useToast } from "@/components/toast";
import { api, messageFrom } from "@/lib/api";
import { useLanguage } from "@/lib/i18n";
import type { Agent } from "@/types";

/** A voice agent's Voice tab: how it sounds and what it says when it picks
 * up. Saving pushes the change to the phone lines it answers. */
export function AgentVoiceTab({ agent, onSaved }: { agent: Agent; onSaved: (agent: Agent) => void }) {
  const { t, lang } = useLanguage();
  const toast = useToast();
  const [voice, setVoice] = useState({ id: agent.voice_id, name: agent.voice_name });
  const [greeting, setGreeting] = useState(agent.greeting);
  const [busy, setBusy] = useState(false);
  const changed = voice.id !== agent.voice_id || greeting.trim() !== agent.greeting;

  async function save() {
    setBusy(true);
    try {
      const saved = await api<Agent>(`/agents/${agent.id}`, { method: "PATCH", body: JSON.stringify({ voice_id: voice.id, voice_name: voice.name, greeting: greeting.trim() }) });
      onSaved(saved);
      toast.success(t("phone.agent.saved"));
    } catch (err) { toast.error(messageFrom(err)); } finally { setBusy(false); }
  }

  return <div className="settings-form">
    <section className="settings-section"><div className="settings-copy"><h3>{t("phone.agent.voiceTitle")}</h3><p>{t("phone.agent.voiceCopy")}</p></div>
      <div className="settings-fields">
        <VoicePicker language={agent.prompt_language || lang} value={voice.id} name={voice.name} onChange={setVoice} />
        <label>{t("phone.channel.greetingLabel")}<textarea rows={2} maxLength={600} value={greeting} placeholder={t("phone.channel.greetingPlaceholder")} onChange={(e) => setGreeting(e.target.value)} /></label>
        <span className="field-help">{t("phone.channel.greetingHint")}</span>
      </div>
    </section>
    <div className="sticky-save"><div className="sticky-left" /><button type="button" className="button primary" disabled={busy || !changed} onClick={save}>{busy ? <LoaderCircle className="spin" size={17} /> : <Save size={17} />} {t("phone.agent.save")}</button></div>
  </div>;
}
