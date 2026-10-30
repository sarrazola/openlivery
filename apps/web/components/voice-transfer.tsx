"use client";

import { useState } from "react";
import { LoaderCircle, Save } from "lucide-react";
import { PhoneInput } from "@/components/phone-input";
import { useToast } from "@/components/toast";
import { api, messageFrom } from "@/lib/api";
import { useLanguage } from "@/lib/i18n";
import type { Agent } from "@/types";

/** A voice agent's way to a person: on a call there is no inbox to hand the
 * conversation to, so the call itself is passed to a number while the caller
 * stays on the line. The number is picked with its country, so it reaches
 * ElevenLabs in full international form. */
export function VoiceTransfer({ agent, onSaved }: { agent: Agent; onSaved: (agent: Agent) => void }) {
  const { t, lang } = useLanguage();
  const toast = useToast();
  const [digits, setDigits] = useState((agent.transfer_number || "").replace(/[^0-9]/g, ""));
  const [when, setWhen] = useState(agent.transfer_when || "");
  const [busy, setBusy] = useState(false);
  const number = digits ? `+${digits}` : "";
  const changed = number !== (agent.transfer_number || "") || when.trim() !== (agent.transfer_when || "");

  async function save() {
    setBusy(true);
    try {
      const saved = await api<Agent>(`/agents/${agent.id}`, { method: "PATCH", body: JSON.stringify({ transfer_number: number || null, transfer_when: when.trim() }) });
      onSaved(saved);
      toast.success(t("phone.agent.transferSaved"));
    } catch (err) { toast.error(messageFrom(err)); } finally { setBusy(false); }
  }

  return <section className="settings-section"><div className="settings-copy"><h3>{t("phone.agent.transferTitle")}</h3><p>{t("phone.agent.transferCopy")}</p></div>
    <div className="settings-fields">
      <label>{t("phone.agent.transferNumber")}<PhoneInput name="transfer_number" initial={agent.transfer_number} locale={lang} placeholder={t("phone.agent.transferPlaceholder")} searchPlaceholder={t("portal.contacts.form.searchCountry")} onChange={setDigits} /></label>
      {number && <label>{t("phone.agent.transferWhen")}<textarea rows={2} maxLength={600} value={when} placeholder={t("phone.agent.transferWhenPlaceholder")} onChange={(event) => setWhen(event.target.value)} disabled={busy} /></label>}
      <button type="button" className="button primary align-end" disabled={busy || !changed} onClick={save}>{busy ? <LoaderCircle className="spin" size={16} /> : <Save size={16} />} {t("phone.agent.transferSave")}</button>
    </div>
  </section>;
}
