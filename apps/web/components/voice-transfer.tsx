"use client";

import { useEffect, useImperativeHandle, useRef, useState, type Ref } from "react";
import { PhoneInput } from "@/components/phone-input";
import { Alert } from "@/components/ui";
import { api, messageFrom } from "@/lib/api";
import { useLanguage } from "@/lib/i18n";
import type { SectionHandle } from "@/lib/unsaved";
import type { Agent } from "@/types";

/** A voice agent's way to a person: on a call there is no inbox to hand the
 * conversation to, so the call itself is passed to a number while the caller
 * stays on the line. The number is picked with its country, so it reaches
 * ElevenLabs in full international form. Saved by the page's save button,
 * through `ref`. */
export function VoiceTransfer({ agent, onSaved, ref, onDirty }: { agent: Agent; onSaved: (agent: Agent) => void; ref?: Ref<SectionHandle>; onDirty?: (dirty: boolean) => void }) {
  const { t, lang } = useLanguage();
  const [digits, setDigits] = useState((agent.transfer_number || "").replace(/[^0-9]/g, ""));
  const [when, setWhen] = useState(agent.transfer_when || "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const section = useRef<HTMLElement>(null);
  const number = digits ? `+${digits}` : "";
  const changed = number !== (agent.transfer_number || "") || when.trim() !== (agent.transfer_when || "");
  const notify = useRef(onDirty);
  useEffect(() => { notify.current = onDirty; });
  useEffect(() => { notify.current?.(changed); }, [changed]);
  useEffect(() => () => notify.current?.(false), []);

  async function save() {
    setBusy(true); setError("");
    try {
      onSaved(await api<Agent>(`/agents/${agent.id}`, { method: "PATCH", body: JSON.stringify({ transfer_number: number || null, transfer_when: when.trim() }) }));
      return true;
    } catch (err) {
      setError(messageFrom(err));
      section.current?.scrollIntoView({ behavior: "smooth", block: "center" });
      return false;
    } finally { setBusy(false); }
  }
  useImperativeHandle(ref, () => ({ save }));

  return <section className="settings-section" ref={section}><div className="settings-copy"><h3>{t("phone.agent.transferTitle")}</h3><p>{t("phone.agent.transferCopy")}</p></div>
    <div className="settings-fields">
      <label>{t("phone.agent.transferNumber")}<PhoneInput name="transfer_number" initial={agent.transfer_number} locale={lang} placeholder={t("phone.agent.transferPlaceholder")} searchPlaceholder={t("portal.contacts.form.searchCountry")} onChange={setDigits} /></label>
      {number && <label>{t("phone.agent.transferWhen")}<textarea rows={2} maxLength={600} value={when} placeholder={t("phone.agent.transferWhenPlaceholder")} onChange={(event) => setWhen(event.target.value)} disabled={busy} /></label>}
      {error && <Alert>{error}</Alert>}
    </div>
  </section>;
}
