"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { LoaderCircle, Pencil, Plus, Trash2, Users } from "lucide-react";
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

  return <>
    <div className="portal-teams">
      <div className="portal-contacts-toolbar">
        <span>{t("portal.teams.count", { count: items.length })}</span>
        <button className="button primary small" onClick={() => openEditor("new")}><Plus size={15} /> {t("portal.teams.new")}</button>
      </div>
      {error && !editing && !deleting && <Alert>{error}</Alert>}
      {loading ? <div className="no-conversations"><LoaderCircle className="spin" size={16} /></div>
        : items.length ? <div className="team-grid">
          {items.map((team) => <article key={team.id} className="team-card">
            <header>
              <strong>{team.name}{team.is_default && <span className="mini-badge ai">{t("portal.teams.default")}</span>}</strong>
              <span className="thread-actions">
                <button className="icon-button" onClick={() => openEditor(team)} title={t("portal.teams.edit")} aria-label={t("portal.teams.edit")}><Pencil size={15} /></button>
                <button className="icon-button danger" onClick={() => { setError(""); setDeleting(team); }} title={t("portal.teams.delete")} aria-label={t("portal.teams.delete")}><Trash2 size={15} /></button>
              </span>
            </header>
            {team.description && <p>{team.description}</p>}
            <small>{strategyLabel(team.strategy)} · {t("portal.teams.openCount", { count: team.open_count })}{team.unassigned_count > 0 && <em className="nav-count">{t("portal.teams.unassignedCount", { count: team.unassigned_count })}</em>}</small>
            <div className="team-members">
              {team.members.length ? team.members.map((member) => <span key={member.id} className={`team-member ${member.availability}`}><i />{member.name}</span>)
                : <span className="muted">{t("portal.teams.noMembers")}</span>}
            </div>
          </article>)}
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
        <label>{t("portal.teams.form.members")}</label>
        <div className="merge-candidates">
          {members.map((member) => <button type="button" key={member.id} className={selectedMembers.includes(member.id) ? "active" : ""} onClick={() => setSelectedMembers((list) => toggle(list, member.id))}>
            <i className={`presence-dot ${member.availability}`} />
            <span><strong>{member.name}</strong><small>{member.email}</small></span>
          </button>)}
          {!members.length && <p className="muted">{t("portal.teams.form.noPeople")}</p>}
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
