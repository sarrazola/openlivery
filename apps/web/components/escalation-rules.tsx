"use client";

import { useCallback, useEffect, useState } from "react";
import { tagStyle } from "@/lib/tags";
import { ArrowDown, ArrowUp, LoaderCircle, Plus, Trash2, X } from "lucide-react";
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
  builtin_enabled: boolean;
  rules: Rule[];
};
type Option = { id: string; name: string };
type TagRow = { id: string; name: string; color: string; contact_count: number; route_team_id: string | null; route_team_name: string | null; route_assignee_id: string | null; route_assignee_name: string | null };

/** The bot's escalation rules: WHEN in the business's words (the model reads
 * it contextually), WHERE picked from real teams and people - never guessed.
 * The list is edited as a whole and saved with one button. */
export function EscalationRulesEditor({ agentId, clientId }: { agentId: string; clientId: string }) {
  const t = useT();
  const [rules, setRules] = useState<Rule[]>([]);
  const [builtinOn, setBuiltinOn] = useState(true);
  const [defaultDest, setDefaultDest] = useState("");
  const [teams, setTeams] = useState<Option[]>([]);
  const [people, setPeople] = useState<Option[]>([]);
  const [tags, setTags] = useState<TagRow[]>([]);
  const [newTagId, setNewTagId] = useState("");
  const [newDest, setNewDest] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);

  const load = useCallback(async () => {
    const [config, teamRows, peopleRows, tagRows] = await Promise.all([
      api<Config>(`/agents/${agentId}/escalation-rules`),
      api<Option[]>(`/clients/${clientId}/teams`),
      api<{ id: string; name: string; email: string }[]>(`/clients/${clientId}/portal-users`),
      api<TagRow[]>(`/clients/${clientId}/contact-tags`).catch(() => [] as TagRow[]),
    ]);
    setTags(tagRows);
    setRules(config.rules);
    setBuiltinOn(config.builtin_enabled ?? true);
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
        builtin_enabled: builtinOn,
        rules: ruleRows,
      };
      const saved = await api<Config>(`/agents/${agentId}/escalation-rules`, { method: "PUT", body: JSON.stringify(payload) });
      setRules(saved.rules);
      setBuiltinOn(saved.builtin_enabled ?? true);
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } catch (err) { setError(messageFrom(err)); } finally { setBusy(false); }
  }

  // Routing by tag is a client-level setting saved on the spot: it applies to
  // every agent of the client, before any AI reply.
  async function routeTag(tag: TagRow, destination: string) {
    const [kind, id] = destination.split(":");
    setError("");
    try {
      const updated = await api<TagRow>(`/clients/${clientId}/contact-tags/${tag.id}`, {
        method: "PATCH",
        body: JSON.stringify({ route_team_id: kind === "team" ? id : null, route_assignee_id: kind === "user" ? id : null }),
      });
      setTags((prev) => prev.map((row) => (row.id === updated.id ? updated : row)));
    } catch (err) { setError(messageFrom(err)); }
  }

  const routedTags = tags.filter((tag) => tag.route_team_id || tag.route_assignee_id);
  const unroutedTags = tags.filter((tag) => !tag.route_team_id && !tag.route_assignee_id);
  const hasDestinations = teams.length > 0 || people.length > 0;
  const destinationOptions = <>
    {teams.length > 0 && <optgroup label={t("agents.escalation.groupTeams")}>
      {teams.map((team) => <option key={team.id} value={`team:${team.id}`}>{team.name}</option>)}
    </optgroup>}
    {people.length > 0 && <optgroup label={t("agents.escalation.groupPeople")}>
      {people.map((person) => <option key={person.id} value={`user:${person.id}`}>{person.name}</option>)}
    </optgroup>}
  </>;

  // Three numbered steps, in the order they run: tag routing before the AI,
  // then the built-in escalation, then the agent's own rules.
  return (
    <section className="settings-section">
      <div className="settings-copy">
        <h3>{t("agents.escalation.heading")}</h3>
        <p>{t("agents.escalation.copy")}</p>
      </div>
      <div className="settings-fields esc-steps">
        {loading ? <div className="no-conversations"><LoaderCircle className="spin" size={16} /></div> : <>
          <div className="esc-step">
            <div className="esc-step-head"><span className="esc-step-n">1</span><div><strong>{t("agents.escalation.byTagHeading")}</strong><small>{t("agents.escalation.byTagHint")}</small></div></div>
            <div className="esc-step-body">
              {tags.length === 0 && <p className="esc-empty">{t("agents.escalation.byTagNone")}</p>}
              {tags.length > 0 && routedTags.length === 0 && <p className="esc-empty">{t("agents.escalation.byTagEmpty")}</p>}
              {routedTags.map((tag) => <div key={tag.id} className="esc-row">
                <span className="tag-chip" style={tagStyle(tag.color)}>{tag.name}</span>
                <small>{t("agents.escalation.byTagCount", { count: tag.contact_count })}</small>
                <span className="esc-arrow" aria-hidden="true">→</span>
                <strong className="esc-target">{tag.route_assignee_name ?? tag.route_team_name}</strong>
                <button type="button" className="icon-button" onClick={() => routeTag(tag, "")} title={t("agents.escalation.byTagRemove")} aria-label={t("agents.escalation.byTagRemove")}><X size={14} /></button>
              </div>)}
              {tags.length > 0 && !hasDestinations && <p className="esc-empty">{t("agents.escalation.byTagNoTeams")}</p>}
              {unroutedTags.length > 0 && hasDestinations && <div className="esc-adder">
                <select value={newTagId} onChange={(e) => setNewTagId(e.target.value)} aria-label={t("agents.escalation.byTagPick")}>
                  <option value="">{t("agents.escalation.byTagPick")}</option>
                  {unroutedTags.map((tag) => <option key={tag.id} value={tag.id}>{tag.name}</option>)}
                </select>
                <span className="esc-arrow" aria-hidden="true">→</span>
                <select value={newDest} onChange={(e) => setNewDest(e.target.value)} aria-label={t("agents.escalation.byTagPickTeam")}>
                  <option value="">{t("agents.escalation.byTagPickTeam")}</option>
                  {destinationOptions}
                </select>
                <button type="button" className="button secondary small" disabled={!newTagId || !newDest} onClick={() => { const tag = tags.find((row) => row.id === newTagId); if (tag) { routeTag(tag, newDest); setNewTagId(""); setNewDest(""); } }}><Plus size={14} /> {t("agents.escalation.byTagAdd")}</button>
              </div>}
            </div>
          </div>

          <div className="esc-step">
            <div className="esc-step-head"><span className="esc-step-n">2</span><div><strong>{t("agents.escalation.builtinHeading")}</strong><small>{t("agents.escalation.generalCondition")}</small></div>
              <label className="switch-row esc-toggle"><input type="checkbox" checked={builtinOn} onChange={(e) => setBuiltinOn(e.target.checked)} aria-label={t("agents.escalation.builtinToggle")} /></label>
            </div>
            {builtinOn && <div className="esc-step-body">
              <label className="esc-inline"><span>{t("agents.escalation.generalLabel")}</span>
                <select value={defaultDest} onChange={(e) => setDefaultDest(e.target.value)}>
                  <option value="">{t("agents.escalation.generalFallback")}</option>
                  {destinationOptions}
                </select>
              </label>
            </div>}
          </div>

          <div className="esc-step">
            <div className="esc-step-head"><span className="esc-step-n">3</span><div><strong>{t("agents.escalation.rulesHeading")}</strong><small>{t("agents.escalation.rulesHint")}</small></div></div>
            <div className="esc-step-body">
              {rules.map((rule, index) => (
                <div key={index} className={`esc-rule${rule.is_active ? "" : " inactive"}`}>
                  <span className="esc-rule-n">{index + 1}</span>
                  <input value={rule.condition} onChange={(e) => patch(index, { condition: e.target.value })} placeholder={t("agents.escalation.conditionPlaceholder")} maxLength={2000} aria-label={t("agents.escalation.when")} />
                  <span className="esc-arrow" aria-hidden="true">→</span>
                  <select
                    className={rule.broken ? "broken" : ""}
                    value={destinationOf(rule)}
                    aria-label={t("agents.escalation.sendToLabel")}
                    onChange={(e) => {
                      const [kind, id] = e.target.value.split(":");
                      patch(index, { team_id: kind === "team" ? id : null, assignee_id: kind === "user" ? id : null });
                    }}
                  >
                    <option value="">{rule.broken ? t("agents.escalation.broken") : t("agents.escalation.pickDestination")}</option>
                    {destinationOptions}
                  </select>
                  <span className="escalation-actions">
                    <label className="escalation-active" title={t("agents.escalation.active")}><input type="checkbox" checked={rule.is_active} onChange={(e) => patch(index, { is_active: e.target.checked })} aria-label={t("agents.escalation.active")} /></label>
                    <button type="button" className="icon-button" onClick={() => move(index, -1)} disabled={index === 0} title={t("agents.escalation.moveUp")} aria-label={t("agents.escalation.moveUp")}><ArrowUp size={14} /></button>
                    <button type="button" className="icon-button" onClick={() => move(index, 1)} disabled={index === rules.length - 1} title={t("agents.escalation.moveDown")} aria-label={t("agents.escalation.moveDown")}><ArrowDown size={14} /></button>
                    <button type="button" className="icon-button danger" onClick={() => setRules((list) => list.filter((_, i) => i !== index))} title={t("agents.escalation.remove")} aria-label={t("agents.escalation.remove")}><Trash2 size={14} /></button>
                  </span>
                </div>
              ))}
              {!rules.length && <p className="esc-empty">{t("agents.escalation.empty")}</p>}
              <div className="esc-rules-foot">
                <button type="button" className="button secondary small" onClick={() => setRules((list) => [...list, { condition: "", team_id: null, assignee_id: null, is_active: true }])}><Plus size={14} /> {t("agents.escalation.add")}</button>
              </div>
            </div>
          </div>

          {error && <Alert>{error}</Alert>}
          <div className="form-footer escalation-footer">
            <span className="escalation-save">{saved && <span className="escalation-saved">{t("agents.escalation.savedNote")}</span>}<button type="button" className="button primary" onClick={save} disabled={busy}>{busy ? <LoaderCircle className="spin" size={16} /> : t("agents.escalation.save")}</button></span>
          </div>
        </>}
      </div>
    </section>
  );
}
