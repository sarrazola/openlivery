"use client";

import { useCallback, useEffect, useState } from "react";
import { LoaderCircle } from "lucide-react";
import { Alert } from "@/components/ui";
import { api, messageFrom } from "@/lib/api";
import { useLanguage, useT } from "@/lib/i18n";
import type { PortalReport } from "@/types";

const RANGES = [7, 30, 90] as const;
const STARTED_COLOR = "#635bff";
const RESOLVED_COLOR = "#0f8b76";

function localISO(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function formatSeconds(value: number | null, none: string): string {
  if (value === null) return none;
  const s = Math.round(value);
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.round(s / 60)} min`;
  const hours = Math.floor(s / 3600);
  const minutes = Math.round((s % 3600) / 60);
  return minutes ? `${hours} h ${minutes} min` : `${hours} h`;
}

export function ReportsView({ slug }: { slug: string }) {
  const t = useT();
  const { lang } = useLanguage();
  const [days, setDays] = useState<number>(7);
  const [report, setReport] = useState<PortalReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    const to = new Date();
    const from = new Date();
    from.setDate(to.getDate() - (days - 1));
    const params = new URLSearchParams({ from: localISO(from), to: localISO(to), tz_offset: String(to.getTimezoneOffset()) });
    setReport(await api<PortalReport>(`/portal/${slug}/reports?${params}`));
  }, [slug, days]);
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

  if (loading) return <div className="no-conversations"><LoaderCircle className="spin" size={16} /></div>;
  if (error) return <Alert>{error}</Alert>;
  if (!report) return null;

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
    <div className="report-ranges">
      {RANGES.map((value) => <button key={value} type="button" className={value === days ? "active" : ""} onClick={() => setDays(value)}>
        {value === 7 ? t("portal.reports.range7") : value === 30 ? t("portal.reports.range30") : t("portal.reports.range90")}
      </button>)}
    </div>

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
          <small>{i % labelStep === 0 ? dayLabel(day.date) : " "}</small>
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
