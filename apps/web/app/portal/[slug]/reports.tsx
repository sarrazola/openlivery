"use client";

import { useCallback, useEffect, useState } from "react";
import { LoaderCircle } from "lucide-react";
import { Alert } from "@/components/ui";
import { api, messageFrom } from "@/lib/api";
import { useLanguage, useT } from "@/lib/i18n";
import type { PortalReport, Team } from "@/types";

const RANGES = [7, 30, 90] as const;
const CHANNELS = ["whatsapp", "whatsapp_cloud", "widget", "playground"] as const;
const STARTED_COLOR = "#635bff";
const RESOLVED_COLOR = "#0f8b76";

type Member = { id: string; name: string; email: string };

function localISO(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function daysAgoISO(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() - days);
  return localISO(d);
}

function formatSeconds(value: number | null, none: string): string {
  if (value === null) return none;
  const s = Math.round(value);
  if (s < 60) return `${s}s`;
  const totalMinutes = Math.round(s / 60);
  if (totalMinutes < 60) return `${totalMinutes} min`;
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  return minutes ? `${hours} h ${minutes} min` : `${hours} h`;
}

export function ReportsView({ slug }: { slug: string }) {
  const t = useT();
  const { lang } = useLanguage();
  const [range, setRange] = useState<number | "custom">(7);
  const [customFrom, setCustomFrom] = useState(daysAgoISO(6));
  const [customTo, setCustomTo] = useState(daysAgoISO(0));
  const [channel, setChannel] = useState("");
  const [assigneeId, setAssigneeId] = useState("");
  const [teamId, setTeamId] = useState("");
  const [members, setMembers] = useState<Member[]>([]);
  const [teams, setTeams] = useState<Team[]>([]);
  const [report, setReport] = useState<PortalReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    api<Member[]>(`/portal/${slug}/members`).then(setMembers).catch(() => {});
    api<Team[]>(`/portal/${slug}/teams`).then(setTeams).catch(() => {});
  }, [slug]);

  const load = useCallback(async () => {
    const from = range === "custom" ? customFrom : daysAgoISO(range - 1);
    const to = range === "custom" ? customTo : daysAgoISO(0);
    if (!from || !to || from > to) return;
    const params = new URLSearchParams({ from, to, tz_offset: String(new Date().getTimezoneOffset()) });
    if (channel) params.set("channel", channel);
    if (assigneeId) params.set("assignee_id", assigneeId);
    if (teamId) params.set("team_id", teamId);
    setReport(await api<PortalReport>(`/portal/${slug}/reports?${params}`));
  }, [slug, range, customFrom, customTo, channel, assigneeId, teamId]);
  useEffect(() => {
    setLoading(true); setError("");
    load().catch((err) => setError(messageFrom(err))).finally(() => setLoading(false));
  }, [load]);

  const dayLabel = (iso: string) => new Date(`${iso}T00:00`).toLocaleDateString(lang === "es" ? "es" : "en", { day: "numeric", month: "short" });
  const channelLabel = (value: string) => {
    if (value === "playground") return t("inbox.channelPlayground");
    if (value === "whatsapp") return t("inbox.channelWhatsapp");
    if (value === "whatsapp_cloud") return t("inbox.channelWhatsappCloud");
    if (value === "widget") return t("inbox.channelWidget");
    return value;
  };

  const filters = <div className="report-filters">
    <div className="report-ranges">
      {RANGES.map((value) => <button key={value} type="button" className={value === range ? "active" : ""} onClick={() => setRange(value)}>
        {value === 7 ? t("portal.reports.range7") : value === 30 ? t("portal.reports.range30") : t("portal.reports.range90")}
      </button>)}
      <button type="button" className={range === "custom" ? "active" : ""} onClick={() => setRange("custom")}>{t("portal.reports.rangeCustom")}</button>
    </div>
    {range === "custom" && <div className="report-custom-range">
      <input type="date" value={customFrom} max={customTo || undefined} onChange={(e) => setCustomFrom(e.target.value)} aria-label={t("portal.reports.fromDate")} />
      <span>{t("portal.reports.toDate")}</span>
      <input type="date" value={customTo} min={customFrom || undefined} max={daysAgoISO(0)} onChange={(e) => setCustomTo(e.target.value)} aria-label={t("portal.reports.toDate")} />
    </div>}
    <div className="report-selects">
      <select value={channel} onChange={(e) => setChannel(e.target.value)} aria-label={t("portal.reports.channels")}>
        <option value="">{t("portal.reports.filterChannelAll")}</option>
        {CHANNELS.map((value) => <option key={value} value={value}>{channelLabel(value)}</option>)}
      </select>
      <select value={assigneeId} onChange={(e) => setAssigneeId(e.target.value)} aria-label={t("portal.reports.colAgent")}>
        <option value="">{t("portal.reports.filterAgentAll")}</option>
        {members.map((member) => <option key={member.id} value={member.id}>{member.name || member.email}</option>)}
      </select>
      <select value={teamId} onChange={(e) => setTeamId(e.target.value)} aria-label={t("portal.reports.filterTeamAll")}>
        <option value="">{t("portal.reports.filterTeamAll")}</option>
        {teams.map((team) => <option key={team.id} value={team.id}>{team.name}</option>)}
      </select>
    </div>
  </div>;

  if (loading && !report) return <div className="portal-reports">{filters}<div className="no-conversations"><LoaderCircle className="spin" size={16} /></div></div>;
  if (error) return <div className="portal-reports">{filters}<Alert>{error}</Alert></div>;
  if (!report) return <div className="portal-reports">{filters}</div>;

  const maxDay = Math.max(1, ...report.by_day.map((d) => Math.max(d.started, d.resolved)));
  const labelStep = Math.max(1, Math.ceil(report.by_day.length / 8));
  const maxChannel = Math.max(1, ...report.by_channel.map((c) => c.started));
  const none = "-";
  const tiles: { label: string; value: string }[] = [
    { label: t("portal.reports.started"), value: String(report.started) },
    { label: t("portal.reports.resolved"), value: String(report.resolved) },
    { label: t("portal.reports.openNow"), value: String(report.open_now) },
    { label: t("portal.reports.agentsOnline"), value: String(report.agents_online) },
    { label: t("portal.reports.inbound"), value: String(report.inbound_messages) },
    { label: t("portal.reports.humanReplies"), value: String(report.human_replies) },
    { label: t("portal.reports.aiReplies"), value: String(report.ai_replies) },
    { label: t("portal.reports.contacts"), value: String(report.active_contacts) },
    { label: t("portal.reports.firstReply"), value: formatSeconds(report.avg_first_reply_seconds, none) },
    { label: t("portal.reports.resolutionTime"), value: formatSeconds(report.avg_resolution_seconds, none) },
  ];

  return <div className="portal-reports">
    {filters}

    <div className="report-tiles">
      {tiles.map((tile) => <div key={tile.label} className="report-tile"><small>{tile.label}</small><strong>{tile.value}</strong></div>)}
    </div>

    <section className="report-card">
      <header>
        <h3>{t("portal.reports.perDay")}</h3>
        <div className="report-legend">
          <span><i style={{ background: STARTED_COLOR }} /> {t("portal.reports.legendStarted")}</span>
          <span><i style={{ background: RESOLVED_COLOR }} /> {t("portal.reports.legendResolved")}</span>
        </div>
      </header>
      {report.started || report.resolved ? <div className="report-chart" role="img" aria-label={t("portal.reports.perDay")}>
        {report.by_day.map((day, i) => <div key={day.date} className="report-chart-group">
          <div className="report-chart-tip">
            <strong>{dayLabel(day.date)}</strong>
            <span>{t("portal.reports.legendStarted")}: {day.started}</span>
            <span>{t("portal.reports.legendResolved")}: {day.resolved}</span>
          </div>
          <div className="report-chart-bars">
            <i style={{ height: `${(day.started / maxDay) * 100}%`, background: STARTED_COLOR }} />
            <i style={{ height: `${(day.resolved / maxDay) * 100}%`, background: RESOLVED_COLOR }} />
          </div>
          <small>{i % labelStep === 0 ? dayLabel(day.date) : " "}</small>
        </div>)}
      </div> : <p className="muted">{t("portal.reports.noActivity")}</p>}
    </section>

    <div className="report-columns">
      <section className="report-card">
        <header><h3>{t("portal.reports.channels")}</h3></header>
        {report.by_channel.length ? <div className="report-channels">
          {report.by_channel.map((row) => <div key={row.channel}>
            <span>{channelLabel(row.channel)}</span>
            <div className="report-channel-bar"><i style={{ width: `${(row.started / maxChannel) * 100}%` }} /></div>
            <strong>{row.started}</strong>
          </div>)}
        </div> : <p className="muted">{t("portal.reports.noActivity")}</p>}
      </section>

      <section className="report-card">
        <header><h3>{t("portal.reports.team")}</h3></header>
        {report.by_agent.length ? <div className="table-shell report-table">
          <table className="data-table">
            <thead><tr><th>{t("portal.reports.colAgent")}</th><th>{t("portal.reports.colReplies")}</th><th>{t("portal.reports.colAssigned")}</th><th>{t("portal.reports.colOpen")}</th></tr></thead>
            <tbody>{report.by_agent.map((row) => <tr key={row.name}>
              <td><span className={`report-agent ${row.availability}`}><i />{row.name}</span></td>
              <td>{row.replies}</td>
              <td>{row.assigned}</td>
              <td>{row.open_now}</td>
            </tr>)}</tbody>
          </table>
        </div> : <p className="muted">{t("portal.reports.noActivity")}</p>}
      </section>
    </div>
  </div>;
}
