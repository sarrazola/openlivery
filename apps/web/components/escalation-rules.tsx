"use client";

import { useCallback, useEffect, useState } from "react";
import { ArrowDown, ArrowUp, LoaderCircle, Plus, Trash2 } from "lucide-react";
import { Alert } from "@/components/ui";
import { api, messageFrom } from "@/lib/api";
import { useT } from "@/lib/i18n";

type Rule = {
  condition: string;
  team_id: string | null;
  assignee_id: string | null;
  is_active: boolean;
  broken?: boolean;
};
type Config = {
  default_team_id: string | null;
  default_assignee_id: string | null;
  rules: Rule[];
};
type Option = { id: string; name: string };

/** The bot's escalation rules: WHEN in the business's words (the model reads
 * it contextually), WHERE picked from real teams and people - never guessed.
 * The list is edited as a whole and saved with one button. */
export function EscalationRulesEditor({ agentId, clientId }: { agentId: string; clientId: string }) {
  const t = useT();
  const [rules, setRules] = useState<Rule[]>([]);
  const [defaultDest, setDefaultDest] = useState("");
  const [teams, setTeams] = useState<Option[]>([]);
  const [people, setPeople] = useState<Option[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);

  const load = useCallback(async () => {
    const [config, teamRows, peopleRows] = await Promise.all([
      api<Config>(`/agents/${agentId}/escalation-rules`),
      api<Option[]>(`/clients/${clientId}/teams`),
      api<{ id: string; name: string; email: string }[]>(`/clients/${clientId}/portal-users`),
    ]);
    setRules(config.rules);
    setDefaultDest(config.default_team_id ? `team:${config.default_team_id}` : config.default_assignee_id ? `user:${config.default_assignee_id}` : "");
    setTeams(teamRows);
    setPeople(peopleRows.map((row) => ({ id: row.id, name: row.name.trim() || row.email })));
  }, [agentId, clientId]);

  useEffect(() => {
    setLoading(true);
    load().catch((err) => setError(messageFrom(err))).finally(() => setLoading(false));
  }, [load]);

  const destinationOf = (rule: Rule) => (rule.team_id ? `team:${rule.team_id}` : rule.assignee_id ? `user:${rule.assignee_id}` : "");
  const patch = (index: number, changes: Partial<Rule>) =>
    setRules((list) => list.map((rule, i) => (i === index ? { ...rule, ...changes, broken: false } : rule)));
  const move = (index: number, delta: number) =>
    setRules((list) => {
      const next = [...list];
      const target = index + delta;
      if (target < 0 || target >= next.length) return list;
      [next[index], next[target]] = [next[target], next[index]];
      return next;
    });

  async function save() {
    setBusy(true); setError(""); setSaved(false);
    try {
      const ruleRows = rules
        .filter((rule) => rule.condition.trim())
        .map((rule) => ({ condition: rule.condition.trim(), team_id: rule.team_id, assignee_id: rule.assignee_id, is_active: rule.is_active }));
      if (ruleRows.some((rule) => !rule.team_id && !rule.assignee_id)) {
        setError(t("agents.escalation.missingDestination"));
        return;
      }
      const [defaultKind, defaultId] = defaultDest.split(":");
      const payload = {
        default_team_id: defaultKind === "team" ? defaultId : null,
        default_assignee_id: defaultKind === "user" ? defaultId : null,
        rules: ruleRows,
      };
      const saved = await api<Config>(`/agents/${agentId}/escalation-rules`, { method: "PUT", body: JSON.stringify(payload) });
      setRules(saved.rules);
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } catch (err) { setError(messageFrom(err)); } finally { setBusy(false); }
  }

  return (
    <section className="settings-section">
      <div className="settings-copy">
        <h3>{t("agents.escalation.heading")}</h3>
        <p>{t("agents.escalation.copy")}</p>
      </div>
      <div className="settings-fields">
        {loading ? <div className="no-conversations"><LoaderCircle className="spin" size={16} /></div> : <>
          <div className="escalation-rules">
            <div className="escalation-rule general">
              <span className="escalation-when">{t("agents.escalation.when")}</span>
              <span className="escalation-general-text">{t("agents.escalation.generalCondition")}</span>
              <span className="escalation-then">{t("agents.escalation.sendTo")}</span>
              <select value={defaultDest} onChange={(e) => setDefaultDest(e.target.value)} aria-label={t("agents.escalation.generalLabel")}>
                <option value="">{t("agents.escalation.generalFallback")}</option>
                {teams.length > 0 && <optgroup label={t("agents.escalation.groupTeams")}>
                  {teams.map((team) => <option key={team.id} value={`team:${team.id}`}>{team.name}</option>)}
                </optgroup>}
                {people.length > 0 && <optgroup label={t("agents.escalation.groupPeople")}>
                  {people.map((person) => <option key={person.id} value={`user:${person.id}`}>{person.name}</option>)}
                </optgroup>}
              </select>
              <span className="mini-badge ai">{t("agents.escalation.alwaysOn")}</span>
            </div>
            {rules.map((rule, index) => (
              <div key={index} className={`escalation-rule${rule.is_active ? "" : " inactive"}`}>
                <span className="escalation-when">{t("agents.escalation.when")}</span>
                <input
                  value={rule.condition}
                  onChange={(e) => patch(index, { condition: e.target.value })}
                  placeholder={t("agents.escalation.conditionPlaceholder")}
                  maxLength={2000}
                />
                <span className="escalation-then">{t("agents.escalation.sendTo")}</span>
                <select
                  value={destinationOf(rule)}
                  onChange={(e) => {
                    const [kind, id] = e.target.value.split(":");
                    patch(index, { team_id: kind === "team" ? id : null, assignee_id: kind === "user" ? id : null });
                  }}
                >
                  <option value="">{t("agents.escalation.pickDestination")}</option>
                  {teams.length > 0 && <optgroup label={t("agents.escalation.groupTeams")}>
                    {teams.map((team) => <option key={team.id} value={`team:${team.id}`}>{team.name}</option>)}
                  </optgroup>}
                  {people.length > 0 && <optgroup label={t("agents.escalation.groupPeople")}>
                    {people.map((person) => <option key={person.id} value={`user:${person.id}`}>{person.name}</option>)}
                  </optgroup>}
                </select>
                {rule.broken && <span className="mini-badge resolved">{t("agents.escalation.broken")}</span>}
                <span className="escalation-actions">
                  <button type="button" className="icon-button" onClick={() => move(index, -1)} disabled={index === 0} title={t("agents.escalation.moveUp")} aria-label={t("agents.escalation.moveUp")}><ArrowUp size={14} /></button>
                  <button type="button" className="icon-button" onClick={() => move(index, 1)} disabled={index === rules.length - 1} title={t("agents.escalation.moveDown")} aria-label={t("agents.escalation.moveDown")}><ArrowDown size={14} /></button>
                  <label className="escalation-active" title={t("agents.escalation.active")}>
                    <input type="checkbox" checked={rule.is_active} onChange={(e) => patch(index, { is_active: e.target.checked })} />
                  </label>
                  <button type="button" className="icon-button danger" onClick={() => setRules((list) => list.filter((_, i) => i !== index))} title={t("agents.escalation.remove")} aria-label={t("agents.escalation.remove")}><Trash2 size={14} /></button>
                </span>
              </div>
            ))}
          </div>
          <div className="escalation-toolbar">
            <button type="button" className="button small" onClick={() => setRules((list) => [...list, { condition: "", team_id: null, assignee_id: null, is_active: true }])}><Plus size={15} /> {t("agents.escalation.add")}</button>
            <button type="button" className="button primary small" onClick={save} disabled={busy}>{busy ? <LoaderCircle className="spin" size={15} /> : t("agents.escalation.save")}</button>
            {saved && <span className="escalation-saved">{t("agents.escalation.savedNote")}</span>}
          </div>
          {error && <Alert>{error}</Alert>}
          <span className="field-help">{t("agents.escalation.builtinNote")}</span>
        </>}
      </div>
    </section>
  );
}
