"use client";

import { useState } from "react";
import { LoaderCircle, Save } from "lucide-react";
import { useToast } from "@/components/toast";
import { api, messageFrom } from "@/lib/api";
import { useT } from "@/lib/i18n";
import type { Agent } from "@/types";

/** A voice agent's way to a person: on a call there is no inbox to hand the
 * conversation to, so the call itself is passed to a number while the caller
 * stays on the line. */
export function VoiceTransfer({ agent, onSaved }: { agent: Agent; onSaved: (agent: Agent) => void }) {
  const t = useT();
  const toast = useToast();
  const [number, setNumber] = useState(agent.transfer_number || "");
  const [when, setWhen] = useState(agent.transfer_when || "");
  const [busy, setBusy] = useState(false);
  const changed = number.trim() !== (agent.transfer_number || "") || when.trim() !== (agent.transfer_when || "");

  async function save() {
    setBusy(true);
    try {
      const saved = await api<Agent>(`/agents/${agent.id}`, { method: "PATCH", body: JSON.stringify({ transfer_number: number.trim() || null, transfer_when: when.trim() }) });
      setNumber(saved.transfer_number || "");
      onSaved(saved);
      toast.success(t("phone.agent.transferSaved"));
    } catch (err) { toast.error(messageFrom(err)); } finally { setBusy(false); }
  }

  return <section className="settings-section"><div className="settings-copy"><h3>{t("phone.agent.transferTitle")}</h3><p>{t("phone.agent.transferCopy")}</p></div>
    <div className="settings-fields">
      <label>{t("phone.agent.transferNumber")}<input value={number} maxLength={32} placeholder={t("phone.agent.transferPlaceholder")} onChange={(event) => setNumber(event.target.value)} disabled={busy} /></label>
      {number.trim() && <label>{t("phone.agent.transferWhen")}<textarea rows={2} maxLength={600} value={when} placeholder={t("phone.agent.transferWhenPlaceholder")} onChange={(event) => setWhen(event.target.value)} disabled={busy} /></label>}
      <button type="button" className="button primary align-end" disabled={busy || !changed} onClick={save}>{busy ? <LoaderCircle className="spin" size={16} /> : <Save size={16} />} {t("phone.agent.transferSave")}</button>
    </div>
  </section>;
}
