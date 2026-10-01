"use client";

import { useCallback, useEffect, useState } from "react";
import { LoaderCircle, Plus, Trash2 } from "lucide-react";
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

const MAX_REMINDERS = 2;

/** One rule as the editor holds it: when it fires (in hours; the server keeps
 * minutes), who writes the message, and whether it closes the conversation.
 * Reminders come first; the farewell, when there is one, is always last. */
type Rule = { hours: string; custom: boolean; text: string; closes: boolean };

const toHours = (minutes: number | null) => (minutes == null ? "" : String(Math.round((minutes / 60) * 100) / 100));
const number = (hours: string) => Number(hours.replace(",", "."));
const toMinutes = (hours: string) => (hours.trim() === "" ? null : Math.round(number(hours) * 60));
const ruleOf = (minutes: number, text: string | null, closes: boolean): Rule => ({ hours: toHours(minutes), custom: Boolean(text), text: text ?? "", closes });
const tidy = (hours: number) => String(Math.round(hours * 10) / 10);

/** How this agent's conversations end: whether it may resolve a settled case
 * itself, and what it sends when the customer stops answering. Rules are
 * added one by one: reminders, and a farewell that closes the conversation.
 * Each message is written by the agent from the conversation or sent as a
 * fixed text. Saved as a whole with one button, like the escalation rules. */
export function FollowUpEditor({ agentId }: { agentId: string }) {
  const t = useT();
  const [resolveEnabled, setResolveEnabled] = useState(false);
  const [enabled, setEnabled] = useState(false);
  const [rules, setRules] = useState<Rule[]>([]);
  const [channels, setChannels] = useState<string[]>([]);
  const [limits, setLimits] = useState({ min: 5, max: 23 * 60 });
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);

  const apply = (config: FollowUpConfig) => {
    setResolveEnabled(config.resolve_enabled);
    setEnabled(config.enabled);
    setRules([
      ...(config.first_minutes != null ? [ruleOf(config.first_minutes, config.first_text, false)] : []),
      ...(config.first_minutes != null && config.second_minutes != null ? [ruleOf(config.second_minutes, config.second_text, false)] : []),
      ...(config.close_minutes != null ? [ruleOf(config.close_minutes, config.close_text, true)] : []),
    ]);
    setChannels(config.channels);
    setLimits({ min: config.min_minutes, max: config.max_minutes });
  };
  const load = useCallback(async () => apply(await api<FollowUpConfig>(`/agents/${agentId}/follow-ups`)), [agentId]);
  useEffect(() => {
    setLoading(true);
    load().catch((err) => setError(messageFrom(err))).finally(() => setLoading(false));
  }, [load]);

  const reminders = rules.filter((rule) => !rule.closes);
  const farewell = rules.find((rule) => rule.closes);
  const canAdd = !(reminders.length >= MAX_REMINDERS && farewell);
  const maxHours = limits.max / 60;

  const toggle = (on: boolean) => {
    setEnabled(on);
    // A sequence to start from, so switching it on is one click.
    if (on && !rules.length) setRules([{ hours: "1", custom: false, text: "", closes: false }, { hours: "6", custom: false, text: "", closes: true }]);
  };
  /** The first rule is a reminder, the next one the farewell; after that a
   * reminder goes in before the farewell, which stays last. */
  const add = () => setRules((current) => {
    const last = current[current.length - 1];
    if (!last) return [{ hours: "1", custom: false, text: "", closes: false }];
    const lastHours = number(last.hours) || 0;
    if (!last.closes) return [...current, { hours: tidy(Math.min(maxHours, lastHours ? lastHours + 5 : 6)), custom: false, text: "", closes: true }];
    const before = number(current[current.length - 2]?.hours ?? "") || 0;
    const between = lastHours > before ? (before + lastHours) / 2 : before + 1;
    return [...current.slice(0, -1), { hours: tidy(between), custom: false, text: "", closes: false }, last];
  });
  const edit = (index: number, patch: Partial<Rule>) => setRules((current) => current.map((rule, at) => (at === index ? { ...rule, ...patch } : rule)));
  const toggleGroup = (keys: readonly string[]) => setChannels((current) =>
    keys.some((key) => current.includes(key)) ? current.filter((key) => !keys.includes(key)) : [...current, ...keys]);

  function problem(): string {
    if (!rules.length) return t("agents.followUps.errorRequired");
    const minutes = rules.map((rule) => toMinutes(rule.hours));
    if (minutes.some((value) => value == null)) return t("agents.followUps.errorHours");
    const set = minutes as number[];
    if (set.some((value) => Number.isNaN(value) || value < limits.min || value > limits.max)) return t("agents.followUps.errorRange", { min: String(limits.min), max: String(maxHours) });
    if (set.some((value, index) => index > 0 && value <= set[index - 1])) return t("agents.followUps.errorOrder");
    if (rules.some((rule) => rule.custom && !rule.text.trim())) return t("agents.followUps.errorText");
    return "";
  }

  async function save() {
    const invalid = enabled ? problem() : "";
    setSaved(false);
    if (invalid) { setError(invalid); return; }
    setBusy(true); setError("");
    const [first, second] = reminders;
    const textOf = (rule: Rule | undefined) => (rule?.custom ? rule.text.trim() : null);
    const minutesOf = (rule: Rule | undefined) => { const value = rule ? toMinutes(rule.hours) : null; return value != null && !Number.isNaN(value) ? value : null; };
    try {
      apply(await api<FollowUpConfig>(`/agents/${agentId}/follow-ups`, { method: "PUT", body: JSON.stringify({
        resolve_enabled: resolveEnabled, enabled, channels,
        first_minutes: minutesOf(first), first_text: textOf(first),
        second_minutes: minutesOf(second), second_text: textOf(second),
        close_minutes: minutesOf(farewell), close_text: textOf(farewell),
      }) }));
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } catch (err) { setError(messageFrom(err)); } finally { setBusy(false); }
  }

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
          {enabled && <div className="esc-step">
            <div className="esc-step-head"><div><strong>{t("agents.followUps.rulesHeading")}</strong><small>{t("agents.followUps.rulesHint", { max: String(maxHours) })}</small></div></div>
            <div className="esc-step-body">
              {rules.map((rule, index) => {
                const kind = t(rule.closes ? "agents.followUps.farewell" : "agents.followUps.reminder");
                return <div className="followup-rule-wrap" key={index}>
                  <div className="esc-rule followup-rule">
                    <span className="esc-rule-n">{index + 1}</span>
                    <strong className="followup-kind">{kind}</strong>
                    <span className="followup-after">{t("agents.followUps.afterPrefix")}</span>
                    <input className="followup-hours" type="text" inputMode="decimal" value={rule.hours} aria-label={`${kind}: ${t("agents.followUps.hoursLabel")}`} onChange={(e) => edit(index, { hours: e.target.value })} />
                    <span className="followup-after">{t("agents.followUps.afterSuffix")}</span>
                    <span className="esc-arrow" aria-hidden="true">→</span>
                    <select value={rule.custom ? "text" : "ai"} aria-label={`${kind}: ${t("agents.followUps.writerLabel")}`} onChange={(e) => edit(index, { custom: e.target.value === "text" })}>
                      <option value="ai">{t("agents.followUps.modeAi")}</option>
                      <option value="text">{t("agents.followUps.modeText")}</option>
                    </select>
                    <span className="escalation-actions"><button type="button" className="icon-button danger" title={t("agents.followUps.remove")} aria-label={t("agents.followUps.remove")} onClick={() => setRules((current) => current.filter((_, at) => at !== index))}><Trash2 size={14} /></button></span>
                  </div>
                  {rule.custom && <textarea className="followup-text" rows={2} maxLength={1000} value={rule.text} aria-label={`${kind}: ${t("agents.followUps.modeText")}`} placeholder={t(rule.closes ? "agents.followUps.closePlaceholder" : "agents.followUps.textPlaceholder")} onChange={(e) => edit(index, { text: e.target.value })} />}
                </div>;
              })}
              {!rules.length && <p className="esc-empty">{t("agents.followUps.empty")}</p>}
              {canAdd && <div className="esc-rules-foot"><button type="button" className="button secondary small" onClick={add}><Plus size={14} /> {t("agents.followUps.add")}</button></div>}
              <div className="followup-channels">
                <small>{t("agents.followUps.channelsLabel")}</small>
                {CHANNEL_GROUPS.map((group) => {
                  const on = group.keys.some((key) => channels.includes(key));
                  return <button type="button" key={group.label} className={`chip-toggle${on ? " active" : ""}`} aria-pressed={on} onClick={() => toggleGroup(group.keys)}>{t(group.label)}</button>;
                })}
                {!channels.length && <small className="muted">{t("agents.followUps.allChannels")}</small>}
              </div>
            </div>
          </div>}
          {error && <Alert>{error}</Alert>}
          <div className="form-footer escalation-footer">
            <span className="escalation-save">{saved && <span className="escalation-saved">{t("agents.escalation.savedNote")}</span>}<button type="button" className="button primary" onClick={save} disabled={busy}>{busy ? <LoaderCircle className="spin" size={16} /> : t("agents.followUps.save")}</button></span>
          </div>
        </>}
      </div>
    </section>
  );
}
