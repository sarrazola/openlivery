"use client";

import { useCallback, useEffect, useState, type ReactNode } from "react";
import { Bot, ChevronDown, Clock, Inbox, LoaderCircle, MessageSquareText, MessagesSquare, SlidersHorizontal, Timer, UserRound, Users } from "lucide-react";
import { Alert } from "@/components/ui";
import { ConversationExplorer } from "@/components/reports/conversation-explorer";
import { TimeChart } from "@/components/reports/time-chart";
import { api, messageFrom } from "@/lib/api";
import { useLanguage, useT } from "@/lib/i18n";
import type { ConversationReportRow, PortalReport, Team } from "@/types";

const RANGES = [7, 30, 90] as const;
const CHANNELS = ["whatsapp", "whatsapp_cloud", "instagram", "messenger", "widget", "playground"] as const;
const STARTED_COLOR = "#635bff";
const RESOLVED_COLOR = "#0f8b76";
const INBOUND_COLOR = "#635bff";
const AI_COLOR = "#0f8b76";
const HUMAN_COLOR = "#e0a02e";

type Member = { id: string; name: string; email: string };
type DayKey = "started" | "resolved" | "inbound" | "ai_replies" | "human_replies";
type Series = { key: DayKey; color: string; name: string };
type ChartKind = "conversations" | "messages";

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

export function ReportsView({ slug, openConversation }: { slug: string; openConversation?: (row: ConversationReportRow) => void }) {
  const t = useT();
  const { lang } = useLanguage();
  const locale = lang === "es" ? "es" : "en";
  const [section, setSection] = useState<"summary" | "conversations">("summary");
  const [range, setRange] = useState<number | "custom">(7);
  // Phone only: the filters start folded behind a toggle so the numbers come
  // first. A desktop ignores this and always shows them.
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [customFrom, setCustomFrom] = useState(daysAgoISO(6));
  const [customTo, setCustomTo] = useState(daysAgoISO(0));
  const [channel, setChannel] = useState("");
  const [assigneeId, setAssigneeId] = useState("");
  const [teamId, setTeamId] = useState("");
  const [chart, setChart] = useState<ChartKind>("conversations");
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

  const dayLabel = (iso: string) => new Date(`${iso}T00:00`).toLocaleDateString(locale, { day: "numeric", month: "short" });
  const channelLabel = (value: string) => {
    if (value === "playground") return t("inbox.channelPlayground");
    if (value === "whatsapp") return t("inbox.channelWhatsapp");
    if (value === "whatsapp_cloud") return t("inbox.channelWhatsappCloud");
    if (value === "instagram") return t("social.instagram.title");
    if (value === "messenger") return t("social.messenger.title");
    if (value === "widget") return t("inbox.channelWidget");
    return value;
  };

  const sectionSwitch = <div className="report-ranges report-toggle report-sections">
    <button type="button" className={section === "summary" ? "active" : ""} onClick={() => setSection("summary")}>{t("reports.tabs.summary")}</button>
    <button type="button" className={section === "conversations" ? "active" : ""} onClick={() => setSection("conversations")}>{t("reports.tabs.conversations")}</button>
  </div>;
  if (section === "conversations") {
    return <div className="portal-reports">
      {sectionSwitch}
      <ConversationExplorer basePath={`/portal/${slug}/reports/conversations`} scope="portal"
        options={{ channels: [...CHANNELS], members, teams }} onOpen={openConversation} />
    </div>;
  }

  const filters = <>
    {sectionSwitch}
    <button type="button" className="portal-filters-toggle" aria-expanded={filtersOpen} onClick={() => setFiltersOpen((open) => !open)}>
      <SlidersHorizontal size={16} /><span>{t("portal.inbox.filters.label")}</span><ChevronDown size={18} className={`chevron${filtersOpen ? " open" : ""}`} />
    </button>
    <div className={`report-filters${filtersOpen ? "" : " folded"}`}>
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
    </div>
  </>;

  if (loading && !report) return <div className="portal-reports">{filters}<div className="no-conversations"><LoaderCircle className="spin" size={16} /></div></div>;
  if (error) return <div className="portal-reports">{filters}<Alert>{error}</Alert></div>;
  if (!report) return <div className="portal-reports">{filters}</div>;

  const series: Series[] = chart === "conversations"
    ? [
      { key: "started", color: STARTED_COLOR, name: t("portal.reports.legendStarted") },
      { key: "resolved", color: RESOLVED_COLOR, name: t("portal.reports.legendResolved") },
    ]
    : [
      { key: "inbound", color: INBOUND_COLOR, name: t("portal.reports.legendInbound") },
      { key: "ai_replies", color: AI_COLOR, name: t("portal.reports.legendAi") },
      { key: "human_replies", color: HUMAN_COLOR, name: t("portal.reports.legendHuman") },
    ];
  const hasBars = report.by_day.some((day) => series.some((s) => day[s.key] > 0));
  const maxChannel = Math.max(1, ...report.by_channel.map((c) => c.started));
  const none = "-";
  const aiResolvedPct = report.started ? Math.round((report.ai_resolved / report.started) * 100) : 0;

  const metric = (icon: ReactNode, tone: string, label: string, value: string, hint: string) => (
    <article className="metric-card">
      <span className={`metric-icon ${tone}`}>{icon}</span>
      <div><small>{label}</small><strong>{value}</strong><p>{hint}</p></div>
    </article>
  );

  return <div className="portal-reports">
    {filters}

    <section className="metrics-grid">
      {metric(<MessagesSquare size={20} />, "violet", t("portal.reports.started"), String(report.started), t("portal.reports.startedHint", { n: report.resolved }))}
      {metric(<Bot size={20} />, "green", t("portal.reports.aiResolved"), `${aiResolvedPct}%`, t("portal.reports.aiResolvedHint", { r: report.ai_resolved, t: report.started }))}
      {metric(<UserRound size={20} />, "amber", t("portal.reports.handoffs"), String(report.handoffs), t("portal.reports.handoffsHint", { n: report.agents_online }))}
      {metric(<Inbox size={20} />, "blue", t("portal.reports.openNow"), String(report.open_now), t("portal.reports.openNowHint"))}
      {metric(<MessageSquareText size={20} />, "violet", t("portal.reports.inbound"), String(report.inbound_messages), t("portal.reports.inboundHint", { a: report.ai_replies, h: report.human_replies }))}
      {metric(<Users size={20} />, "blue", t("portal.reports.contacts"), String(report.active_contacts), t("portal.reports.contactsHint"))}
      {metric(<Clock size={20} />, "green", t("portal.reports.firstReply"), formatSeconds(report.avg_first_reply_seconds, none), t("portal.reports.firstReplyHint"))}
      {metric(<Timer size={20} />, "amber", t("portal.reports.resolutionTime"), formatSeconds(report.avg_resolution_seconds, none), t("portal.reports.resolutionTimeHint"))}
    </section>

    <section className="report-card">
      <header>
        <div className="report-ranges report-toggle">
          <button type="button" className={chart === "conversations" ? "active" : ""} onClick={() => setChart("conversations")}>{t("portal.reports.chartConversations")}</button>
          <button type="button" className={chart === "messages" ? "active" : ""} onClick={() => setChart("messages")}>{t("portal.reports.chartMessages")}</button>
        </div>
        <div className="report-legend">
          {series.map((s) => <span key={s.key}><i style={{ background: s.color }} /> {s.name}</span>)}
        </div>
      </header>
      {hasBars ? <TimeChart ariaLabel={t("portal.reports.perDay")}
        points={report.by_day.map((day) => ({ key: day.date, label: dayLabel(day.date), values: series.map((s) => day[s.key]) }))}
        series={series.map((s) => ({ name: s.name, color: s.color }))} /> : <p className="muted">{t("portal.reports.noActivity")}</p>}
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
