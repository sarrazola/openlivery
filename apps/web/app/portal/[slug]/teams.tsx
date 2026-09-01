"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { LoaderCircle, Pencil, Plus, Search, Trash2, Users, X } from "lucide-react";
import { Alert, EmptyState, Modal } from "@/components/ui";
import { api, ApiError, messageFrom } from "@/lib/api";
import { useT } from "@/lib/i18n";
import type { PortalMember, Team } from "@/types";

const STRATEGIES = ["round_robin", "least_busy"] as const;
const CHANNEL_OPTIONS = ["whatsapp", "whatsapp_cloud", "widget"] as const;

export function TeamsView({ slug }: { slug: string }) {
  const t = useT();
  const [items, setItems] = useState<Team[]>([]);
  const [members, setMembers] = useState<PortalMember[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState<Team | "new" | null>(null);
  const [deleting, setDeleting] = useState<Team | null>(null);
  const [selectedMembers, setSelectedMembers] = useState<string[]>([]);
  const [selectedChannels, setSelectedChannels] = useState<string[]>([]);
  const [memberQuery, setMemberQuery] = useState("");
  const [pickerOpen, setPickerOpen] = useState(false);

  const load = useCallback(async () => {
    const [teams, people] = await Promise.all([
      api<Team[]>(`/portal/${slug}/teams`),
      api<PortalMember[]>(`/portal/${slug}/members`),
    ]);
    setItems(teams);
    setMembers(people);
  }, [slug]);

  useEffect(() => {
    setLoading(true);
    load().catch((err) => setError(messageFrom(err))).finally(() => setLoading(false));
  }, [load]);

  function openEditor(team: Team | "new") {
    setError("");
    setEditing(team);
    setSelectedMembers(team === "new" ? [] : team.members.map((member) => member.id));
    setSelectedChannels(team === "new" ? [] : team.channels);
    setMemberQuery("");
  }

  const toggle = (list: string[], value: string) =>
    list.includes(value) ? list.filter((item) => item !== value) : [...list, value];

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const body = {
      name: String(data.get("name") || "").trim(),
      description: String(data.get("description") || "").trim(),
      strategy: String(data.get("strategy") || "round_robin"),
      channels: selectedChannels,
      is_default: data.get("is_default") === "on",
      member_ids: selectedMembers,
    };
    setBusy(true); setError("");
    try {
      if (editing === "new") await api<Team>(`/portal/${slug}/teams`, { method: "POST", body: JSON.stringify(body) });
      else if (editing) await api<Team>(`/portal/${slug}/teams/${editing.id}`, { method: "PATCH", body: JSON.stringify(body) });
      setEditing(null);
      await load();
    } catch (err) {
      setError(err instanceof ApiError && err.status === 409 ? t("portal.teams.duplicateName") : messageFrom(err));
    } finally { setBusy(false); }
  }

  async function remove() {
    if (!deleting) return;
    setBusy(true); setError("");
    try {
      await api(`/portal/${slug}/teams/${deleting.id}`, { method: "DELETE" });
      setDeleting(null);
      await load();
    } catch (err) { setError(messageFrom(err)); } finally { setBusy(false); }
  }

  const strategyLabel = (value: string) =>
    value === "least_busy" ? t("portal.teams.strategy.least_busy") : t("portal.teams.strategy.round_robin");
  const channelLabel = (value: string) =>
    value === "whatsapp" ? t("portal.teams.channel.whatsapp")
    : value === "whatsapp_cloud" ? t("portal.teams.channel.whatsapp_cloud")
    : t("portal.teams.channel.widget");

  const query = memberQuery.trim().toLowerCase();
  const chosenMembers = members.filter((member) => selectedMembers.includes(member.id));
  const memberOptions = members.filter(
    (member) =>
      !selectedMembers.includes(member.id) &&
      (!query || member.name.toLowerCase().includes(query) || member.email.toLowerCase().includes(query))
  );

  return <>
    <div className="portal-teams">
      <div className="portal-contacts-toolbar">
        <span>{t("portal.teams.count", { count: items.length })}</span>
        <button className="button primary small" onClick={() => openEditor("new")}><Plus size={15} /> {t("portal.teams.new")}</button>
      </div>
      {error && !editing && !deleting && <Alert>{error}</Alert>}
      {loading ? <div className="no-conversations"><LoaderCircle className="spin" size={16} /></div>
        : items.length ? <div className="table-shell portal-teams-table">
          <table className="data-table">
            <thead><tr>
              <th>{t("portal.teams.table.name")}</th>
              <th>{t("portal.teams.table.strategy")}</th>
              <th>{t("portal.teams.table.members")}</th>
              <th>{t("portal.teams.table.open")}</th>
              <th />
            </tr></thead>
            <tbody>{items.map((team) => <tr key={team.id}>
              <td className="portal-team-name">
                <strong>{team.name}{team.is_default && <span className="mini-badge ai">{t("portal.teams.default")}</span>}</strong>
                {team.description && <small>{team.description}</small>}
              </td>
              <td>{strategyLabel(team.strategy)}</td>
              <td><div className="team-members">
                {team.members.length ? team.members.map((member) => <span key={member.id} className={`team-member ${member.availability}`}><i />{member.name}</span>)
                  : <span className="muted">{t("portal.teams.noMembers")}</span>}
              </div></td>
              <td>{team.open_count}{team.unassigned_count > 0 && <em className="nav-count">{t("portal.teams.unassignedCount", { count: team.unassigned_count })}</em>}</td>
              <td className="portal-template-actions">
                <button className="icon-button" onClick={() => openEditor(team)} title={t("portal.teams.edit")} aria-label={t("portal.teams.edit")}><Pencil size={15} /></button>
                <button className="icon-button danger" onClick={() => { setError(""); setDeleting(team); }} title={t("portal.teams.delete")} aria-label={t("portal.teams.delete")}><Trash2 size={15} /></button>
              </td>
            </tr>)}</tbody>
          </table>
        </div>
        : <EmptyState icon={<Users />} title={t("portal.teams.emptyTitle")} description={t("portal.teams.emptyDescription")} />}
    </div>

    <Modal open={editing !== null} title={editing === "new" ? t("portal.teams.newTitle") : t("portal.teams.editTitle")} onClose={() => setEditing(null)}>
      <form className="modal-form" onSubmit={save}>
        <div className="form-grid">
          <label>{t("portal.teams.form.name")}<input name="name" required maxLength={120} defaultValue={editing !== "new" && editing ? editing.name : ""} autoFocus /></label>
          <label>{t("portal.teams.form.strategy")}
            <select name="strategy" defaultValue={editing !== "new" && editing ? editing.strategy : "round_robin"}>
              {STRATEGIES.map((value) => <option key={value} value={value}>{strategyLabel(value)}</option>)}
            </select>
          </label>
        </div>
        <label>{t("portal.teams.form.description")}<input name="description" maxLength={500} defaultValue={editing !== "new" && editing ? editing.description : ""} placeholder={t("portal.teams.form.descriptionPlaceholder")} /><span className="field-help">{t("portal.teams.form.descriptionHelp")}</span></label>
        <label>{t("portal.teams.form.members")}{selectedMembers.length > 0 && <span className="muted"> · {t("portal.teams.form.selectedCount", { count: selectedMembers.length })}</span>}</label>
        <div className="member-picker">
          {members.length > 0 && <div className="member-picker-search">
            <Search size={14} />
            <input
              type="search"
              name="member-filter"
              autoComplete="off"
              spellCheck={false}
              value={memberQuery}
              onChange={(e) => setMemberQuery(e.target.value)}
              onFocus={() => setPickerOpen(true)}
              onBlur={() => setPickerOpen(false)}
              placeholder={t("portal.teams.form.searchMembers")}
            />
          </div>}
          {pickerOpen && <div className="member-options">
            {/* onMouseDown so picking wins over the input's blur closing the panel */}
            {memberOptions.map((member) => <button type="button" key={member.id} onMouseDown={(e) => { e.preventDefault(); setSelectedMembers((list) => [...list, member.id]); setMemberQuery(""); }}>
              <i className={`presence-dot ${member.availability}`} />
              <span><strong>{member.name}</strong><small>{member.email}</small></span>
            </button>)}
            {!memberOptions.length && <p className="muted">{query ? t("portal.teams.form.noMatches") : t("portal.teams.form.allAdded")}</p>}
          </div>}
          {!members.length && <p className="muted">{t("portal.teams.form.noPeople")}</p>}
          <div className="member-chips">
            {chosenMembers.map((member) => <span key={member.id} className={`team-member ${member.availability}`}>
              <i />{member.name}
              <button type="button" onClick={() => setSelectedMembers((list) => list.filter((id) => id !== member.id))} title={t("portal.teams.form.removeMember")} aria-label={t("portal.teams.form.removeMember")}><X size={12} /></button>
            </span>)}
            {members.length > 0 && !chosenMembers.length && <span className="muted">{t("portal.teams.noMembers")}</span>}
          </div>
        </div>
        <label>{t("portal.teams.form.channels")}</label>
        <div className="team-channel-options">
          {CHANNEL_OPTIONS.map((channel) => <label key={channel} className="switch-row small">
            <input type="checkbox" checked={selectedChannels.includes(channel)} onChange={() => setSelectedChannels((list) => toggle(list, channel))} />
            <span>{channelLabel(channel)}</span>
          </label>)}
        </div>
        <label className="switch-row small">
          <input type="checkbox" name="is_default" defaultChecked={editing !== "new" && editing ? editing.is_default : false} />
          <span>{t("portal.teams.form.isDefault")}</span>
        </label>
        {error && <Alert>{error}</Alert>}
        <div className="modal-actions"><button type="button" className="button" onClick={() => setEditing(null)}>{t("portal.contacts.form.cancel")}</button><button className="button primary" disabled={busy}>{busy ? <LoaderCircle className="spin" size={16} /> : t("portal.contacts.form.save")}</button></div>
      </form>
    </Modal>

    <Modal open={deleting !== null} title={t("portal.teams.deleteTitle", { name: deleting?.name ?? "" })} description={t("portal.teams.deleteDescription")} onClose={() => setDeleting(null)}>
      <div className="modal-form">
        {error && <Alert>{error}</Alert>}
        <div className="modal-actions"><button type="button" className="button" onClick={() => setDeleting(null)}>{t("portal.contacts.form.cancel")}</button><button className="button danger" disabled={busy} onClick={remove}>{busy ? <LoaderCircle className="spin" size={16} /> : <><Trash2 size={15} /> {t("portal.teams.deleteConfirm")}</>}</button></div>
      </div>
    </Modal>
  </>;
}
