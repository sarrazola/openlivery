"use client";

import { useCallback, useEffect, useState } from "react";
import { Flag, LoaderCircle, MessageCircle, Plus, X } from "lucide-react";
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

const MAX_FOLLOW_UPS = 2;

/** One message of the sequence as the editor holds it: when it goes out (in
 * hours; the server keeps minutes) and who writes it. */
type Step = { hours: string; custom: boolean; text: string };

const toHours = (minutes: number | null) => (minutes == null ? "" : String(Math.round((minutes / 60) * 100) / 100));
const toMinutes = (hours: string) => (hours.trim() === "" ? null : Math.round(Number(hours.replace(",", ".")) * 60));
const stepOf = (minutes: number | null, text: string | null): Step => ({ hours: toHours(minutes), custom: Boolean(text), text: text ?? "" });

/** How this agent's conversations end: whether it may resolve a settled case
 * itself, and what it sends when the customer stops answering. Follow-ups are
 * added one by one, each written by the agent from the conversation or sent
 * as a fixed text; the closing message always comes last. Saved as a whole
 * with one button, like the escalation rules. */
export function FollowUpEditor({ agentId }: { agentId: string }) {
  const t = useT();
  const [resolveEnabled, setResolveEnabled] = useState(false);
  const [enabled, setEnabled] = useState(false);
  const [followUps, setFollowUps] = useState<Step[]>([]);
  const [closing, setClosing] = useState<Step>({ hours: "", custom: false, text: "" });
  const [channels, setChannels] = useState<string[]>([]);
  const [limits, setLimits] = useState({ min: 5, max: 23 * 60 });
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);

  const apply = (config: FollowUpConfig) => {
    setResolveEnabled(config.resolve_enabled);
    setEnabled(config.enabled);
    setFollowUps([
      ...(config.first_minutes != null ? [stepOf(config.first_minutes, config.first_text)] : []),
      ...(config.first_minutes != null && config.second_minutes != null ? [stepOf(config.second_minutes, config.second_text)] : []),
    ]);
    setClosing(stepOf(config.close_minutes, config.close_text));
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
    // A sequence to start from, so switching it on is one click.
    if (on && !followUps.length && !closing.hours) {
      setFollowUps([{ hours: "1", custom: false, text: "" }]);
      setClosing((current) => ({ ...current, hours: "6" }));
    }
  };
  const addFollowUp = () => setFollowUps((current) => {
    const previous = Number(current[current.length - 1]?.hours.replace(",", ".")) || 0;
    return [...current, { hours: String(previous ? previous + 2 : 1), custom: false, text: "" }];
  });
  const editFollowUp = (index: number, patch: Partial<Step>) =>
    setFollowUps((current) => current.map((step, at) => (at === index ? { ...step, ...patch } : step)));
  const toggleGroup = (keys: readonly string[]) => setChannels((current) =>
    keys.some((key) => current.includes(key)) ? current.filter((key) => !keys.includes(key)) : [...current, ...keys]);

  function problem(steps: Step[]): string {
    const range = t("agents.followUps.errorRange", { min: String(limits.min), max: String(limits.max / 60) });
    const minutes = steps.map((step) => toMinutes(step.hours));
    if (minutes.some((value) => value == null)) return t("agents.followUps.errorRequired");
    const set = minutes as number[];
    if (set.some((value) => Number.isNaN(value) || value < limits.min || value > limits.max)) return range;
    if (set.some((value, index) => index > 0 && value <= set[index - 1])) return t("agents.followUps.errorOrder");
    if (steps.some((step) => step.custom && !step.text.trim())) return t("agents.followUps.errorText");
    return "";
  }

  async function save() {
    const steps = [...followUps, closing];
    const invalid = enabled ? problem(steps) : "";
    setSaved(false);
    if (invalid) { setError(invalid); return; }
    setBusy(true); setError("");
    const [first, second] = followUps;
    const textOf = (step: Step | undefined) => (step?.custom ? step.text.trim() : null);
    const minutesOf = (step: Step | undefined) => { const value = step ? toMinutes(step.hours) : null; return value != null && !Number.isNaN(value) ? value : null; };
    try {
      apply(await api<FollowUpConfig>(`/agents/${agentId}/follow-ups`, { method: "PUT", body: JSON.stringify({
        resolve_enabled: resolveEnabled, enabled, channels,
        first_minutes: minutesOf(first), first_text: textOf(first),
        second_minutes: minutesOf(second), second_text: textOf(second),
        close_minutes: minutesOf(closing), close_text: textOf(closing),
      }) }));
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } catch (err) { setError(messageFrom(err)); } finally { setBusy(false); }
  }

  const block = (step: Step, onChange: (patch: Partial<Step>) => void, kind: "first" | "second" | "close", onRemove?: () => void) => {
    const closes = kind === "close";
    const title = closes ? t("agents.followUps.closeTitle") : t(kind === "first" ? "agents.followUps.firstTitle" : "agents.followUps.secondTitle");
    return (
      <div className="followup-step" key={kind}>
        <div className="followup-step-head">
          {closes ? <Flag size={16} /> : <MessageCircle size={16} />}
          <strong>{title}</strong>
          {onRemove && <button type="button" className="icon-button" aria-label={t("agents.followUps.remove")} title={t("agents.followUps.remove")} onClick={onRemove}><X size={15} /></button>}
        </div>
        <div className="followup-when">
          <span>{t("agents.followUps.whenBefore")}</span>
          <input type="text" inputMode="decimal" value={step.hours} aria-label={`${title}: ${t("agents.followUps.hoursLabel")}`} onChange={(e) => onChange({ hours: e.target.value })} />
          <span>{t(closes ? "agents.followUps.whenAfterClose" : "agents.followUps.whenAfterFollowUp")}</span>
        </div>
        <div className="followup-mode">
          <button type="button" className={`chip-toggle${step.custom ? "" : " active"}`} aria-pressed={!step.custom} onClick={() => onChange({ custom: false })}>{t("agents.followUps.modeAi")}</button>
          <button type="button" className={`chip-toggle${step.custom ? " active" : ""}`} aria-pressed={step.custom} onClick={() => onChange({ custom: true })}>{t("agents.followUps.modeText")}</button>
        </div>
        {step.custom && <textarea rows={2} maxLength={1000} value={step.text} aria-label={`${title}: ${t("agents.followUps.modeText")}`} placeholder={t(closes ? "agents.followUps.closePlaceholder" : "agents.followUps.textPlaceholder")} onChange={(e) => onChange({ text: e.target.value })} />}
      </div>
    );
  };

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
            {followUps.map((step, index) => block(step, (patch) => editFollowUp(index, patch), index === 0 ? "first" : "second",
              () => setFollowUps((current) => current.filter((_, at) => at !== index))))}
            {followUps.length < MAX_FOLLOW_UPS && <button type="button" className="button followup-add" onClick={addFollowUp}><Plus size={15} /> {t("agents.followUps.add")}</button>}
            {block(closing, (patch) => setClosing((current) => ({ ...current, ...patch })), "close")}
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
