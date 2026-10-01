"use client";

import { useCallback, useEffect, useState } from "react";
import { LoaderCircle } from "lucide-react";
import { Alert } from "@/components/ui";
import { AiHint } from "@/components/ai-hint";
import { api, messageFrom } from "@/lib/api";
import { useT } from "@/lib/i18n";
import type { FollowUpConfig } from "@/types";

/** Both WhatsApp lines are one choice here, like in the contact details. */
const CHANNEL_GROUPS = [
  { label: "agents.capture.channelWhatsapp", keys: ["whatsapp", "whatsapp_cloud"] },
  { label: "agents.capture.channelInstagram", keys: ["instagram"] },
  { label: "agents.capture.channelMessenger", keys: ["messenger"] },
  { label: "agents.capture.channelWidget", keys: ["widget"] },
] as const;

/** The server keeps minutes; the editor speaks hours. */
const toHours = (minutes: number | null) => (minutes == null ? "" : String(Math.round((minutes / 60) * 100) / 100));
const toMinutes = (hours: string) => (hours.trim() === "" ? null : Math.round(Number(hours.replace(",", ".")) * 60));

/** How this agent's conversations end: whether it may resolve a settled case
 * itself, and what it sends when the customer stops answering. Saved as a
 * whole with one button, like the escalation rules. */
export function FollowUpEditor({ agentId }: { agentId: string }) {
  const t = useT();
  const [resolveEnabled, setResolveEnabled] = useState(false);
  const [enabled, setEnabled] = useState(false);
  const [first, setFirst] = useState("");
  const [second, setSecond] = useState("");
  const [close, setClose] = useState("");
  const [channels, setChannels] = useState<string[]>([]);
  const [limits, setLimits] = useState({ min: 5, max: 23 * 60 });
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);

  const apply = (config: FollowUpConfig) => {
    setResolveEnabled(config.resolve_enabled);
    setEnabled(config.enabled);
    setFirst(toHours(config.first_minutes));
    setSecond(toHours(config.second_minutes));
    setClose(toHours(config.close_minutes));
    setChannels(config.channels);
    setLimits({ min: config.min_minutes, max: config.max_minutes });
  };
  const load = useCallback(async () => apply(await api<FollowUpConfig>(`/agents/${agentId}/follow-ups`)), [agentId]);
  useEffect(() => {
    setLoading(true);
    load().catch((err) => setError(messageFrom(err))).finally(() => setLoading(false));
  }, [load]);

  const toggle = (on: boolean) => {
    setEnabled(on);
    // A schedule to start from, so switching it on is one click.
    if (on && !first && !close) { setFirst("1"); setClose("6"); }
  };
  const toggleGroup = (keys: readonly string[]) => setChannels((current) =>
    keys.some((key) => current.includes(key)) ? current.filter((key) => !keys.includes(key)) : [...current, ...keys]);

  function problem(values: (number | null)[]): string {
    const [firstMinutes, , closeMinutes] = values;
    if (values.some((value) => value != null && Number.isNaN(value))) return t("agents.followUps.errorRange", { min: String(limits.min), max: String(limits.max / 60) });
    if (enabled && (firstMinutes == null || closeMinutes == null)) return t("agents.followUps.errorRequired");
    const set = values.filter((value): value is number => value != null);
    if (set.some((value) => value < limits.min || value > limits.max)) return t("agents.followUps.errorRange", { min: String(limits.min), max: String(limits.max / 60) });
    if (set.some((value, index) => index > 0 && value <= set[index - 1])) return t("agents.followUps.errorOrder");
    return "";
  }

  async function save() {
    const values = [toMinutes(first), toMinutes(second), toMinutes(close)];
    const invalid = problem(values);
    setSaved(false);
    if (invalid) { setError(invalid); return; }
    setBusy(true); setError("");
    try {
      apply(await api<FollowUpConfig>(`/agents/${agentId}/follow-ups`, { method: "PUT", body: JSON.stringify({
        resolve_enabled: resolveEnabled, enabled, first_minutes: values[0], second_minutes: values[1], close_minutes: values[2], channels,
      }) }));
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } catch (err) { setError(messageFrom(err)); } finally { setBusy(false); }
  }

  const time = (label: string, value: string, onChange: (next: string) => void) => (
    <label>{label}<span className="with-unit"><input type="text" inputMode="decimal" value={value} onChange={(e) => onChange(e.target.value)} />{t("agents.followUps.hoursUnit")}</span></label>
  );

  return (
    <section className="settings-section">
      <div className="settings-copy">
        <h3>{t("agents.followUps.heading")} <AiHint text={t("agents.followUps.aiHint")} /></h3>
        <p>{t("agents.followUps.copy")}</p>
      </div>
      <div className="settings-fields capture-editor">
        {loading ? <div className="no-conversations"><LoaderCircle className="spin" size={16} /></div> : <>
          <label className="switch-row"><span><strong>{t("agents.followUps.resolveToggle")}</strong><small>{t("agents.followUps.resolveHint")}</small></span><input type="checkbox" checked={resolveEnabled} onChange={(e) => setResolveEnabled(e.target.checked)} /></label>
          <label className="switch-row"><span><strong>{t("agents.followUps.toggle")}</strong><small>{t("agents.followUps.toggleHint")}</small></span><input type="checkbox" checked={enabled} onChange={(e) => toggle(e.target.checked)} /></label>
          {enabled && <>
            <div className="followup-times">
              {time(t("agents.followUps.first"), first, setFirst)}
              {time(t("agents.followUps.second"), second, setSecond)}
              {time(t("agents.followUps.close"), close, setClose)}
            </div>
            <span className="field-help">{t("agents.followUps.timingHelp", { max: String(limits.max / 60) })}</span>
            <div className="followup-channels">
              <small>{t("agents.followUps.channelsLabel")}</small>
              {CHANNEL_GROUPS.map((group) => {
                const on = group.keys.some((key) => channels.includes(key));
                return <button type="button" key={group.label} className={`chip-toggle${on ? " active" : ""}`} aria-pressed={on} onClick={() => toggleGroup(group.keys)}>{t(group.label)}</button>;
              })}
              {!channels.length && <small className="muted">{t("agents.followUps.allChannels")}</small>}
            </div>
          </>}
          {error && <Alert>{error}</Alert>}
          <div className="form-footer escalation-footer">
            <span className="escalation-save">{saved && <span className="escalation-saved">{t("agents.escalation.savedNote")}</span>}<button type="button" className="button primary" onClick={save} disabled={busy}>{busy ? <LoaderCircle className="spin" size={16} /> : t("agents.followUps.save")}</button></span>
          </div>
        </>}
      </div>
    </section>
  );
}
