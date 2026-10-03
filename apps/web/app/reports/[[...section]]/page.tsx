"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle, Bot, Clock, Coins, Download, Inbox, LoaderCircle, MessageSquareText, Search, Sparkles, UserRound, Users } from "lucide-react";
import { EmptyState, PageHead } from "@/components/ui";
import { ConversationExplorer } from "@/components/reports/conversation-explorer";
import { ControlsRow, FilterSelect, PeriodControl, ReportControls, Segmented } from "@/components/reports/filter-bar";
import { TimeChart } from "@/components/reports/time-chart";
import { useToast } from "@/components/toast";
import { currentSections, showSections } from "@/lib/section-path";
import { api, apiUrl, messageFrom } from "@/lib/api";
import { useLanguage } from "@/lib/i18n";
import type { CostReport, Operations, OpsGroup, ReportFilters, ReportGroup, ReportReply } from "@/types";

const RANGES = [7, 30, 90] as const;
const BUCKETS = ["day", "week", "month", "year"] as const;
const PAGE = 25;
const REFRESH_MS = 30_000;

function localISO(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
function daysAgoISO(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() - days);
  return localISO(d);
}
function money(value: number): string {
  if (value === 0) return "$0";
  if (value < 0.01) return `$${value.toFixed(8).replace(/0+$/, "")}`;
  if (value < 1) return `$${value.toFixed(4)}`;
  return `$${value.toFixed(2)}`;
}

type ReportTab = "summary" | "costs" | "conversations";
const REPORT_TABS: ReportTab[] = ["summary", "costs", "conversations"];

export default function ReportsPage() {
  const { t, lang } = useLanguage();
  const toast = useToast();
  const locale = lang === "es" ? "es" : "en";
  const [tab, setTab] = useState<ReportTab>("summary");
  const [range, setRange] = useState<number | "custom">(30);
  const [customFrom, setCustomFrom] = useState(daysAgoISO(29));
  const [customTo, setCustomTo] = useState(daysAgoISO(0));
  const [clientId, setClientId] = useState("");
  const [agentId, setAgentId] = useState("");
  const [model, setModel] = useState("");
  const [channel, setChannel] = useState("");
  const [bucket, setBucket] = useState<(typeof BUCKETS)[number]>("day");
  const [query, setQuery] = useState("");
  const [filters, setFilters] = useState<ReportFilters | null>(null);
  const [ops, setOps] = useState<Operations | null>(null);
  const [report, setReport] = useState<CostReport | null>(null);
  const [rows, setRows] = useState<ReportReply[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [loading, setLoading] = useState(true);
  // The open tab rides in the address (`/reports/costs`).
  useEffect(() => {
    const [section] = currentSections("/reports");
    const wanted = section && (REPORT_TABS as string[]).includes(section) ? section as ReportTab : "summary";
    setTab(wanted);
    showSections("/reports", [wanted]);
  }, []);
  const changeTab = (next: ReportTab) => { setLoading(next !== "conversations"); setTab(next); showSections("/reports", [next]); };
  const [exporting, setExporting] = useState(false);

  useEffect(() => { api<ReportFilters>("/reports/filters").then(setFilters).catch(() => {}); }, []);

  const from = range === "custom" ? customFrom : daysAgoISO(range - 1);
  const to = range === "custom" ? customTo : daysAgoISO(0);
  const tz = useMemo(() => Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC", []);
  const scope = useMemo(() => {
    const p = new URLSearchParams({ from, to, tz });
    if (clientId) p.set("client_id", clientId);
    if (agentId) p.set("agent_id", agentId);
    return p;
  }, [from, to, tz, clientId, agentId]);
  const replyParams = useMemo(() => {
    const p = new URLSearchParams(scope);
    if (model) p.set("model", model);
    if (query.trim()) p.set("q", query.trim());
    return p;
  }, [scope, model, query]);

  useEffect(() => { setPage(0); }, [replyParams]);

  const load = useCallback(async () => {
    if (!from || !to) return;
    if (tab === "conversations") return;
    if (tab === "summary") {
      const p = new URLSearchParams(scope);
      if (channel) p.set("channel", channel);
      p.set("bucket", bucket);
      setOps(await api<Operations>(`/reports/operations?${p}`));
    } else {
      const p = new URLSearchParams(scope);
      if (model) p.set("model", model);
      const [summary, replies] = await Promise.all([
        api<CostReport>(`/reports/costs?${p}`),
        api<{ items: ReportReply[]; total: number }>(`/reports/replies?${replyParams}&limit=${PAGE}&offset=${page * PAGE}`),
      ]);
      setReport(summary);
      setRows(replies.items);
      setTotal(replies.total);
    }
  }, [tab, from, to, scope, channel, bucket, model, replyParams, page]);

  useEffect(() => {
    let cancelled = false;
    load().catch((err) => { if (!cancelled) toast.error(messageFrom(err)); }).finally(() => { if (!cancelled) setLoading(false); });
    const timer = setInterval(() => { load().catch(() => {}); }, REFRESH_MS);
    return () => { cancelled = true; clearInterval(timer); };
  }, [load, toast]);

  const exportCsv = useCallback(async () => {
    setExporting(true);
    try {
      const response = await fetch(apiUrl(`/reports/replies?${replyParams}&format=csv`), { credentials: "include" });
      if (!response.ok) throw new Error("Export failed");
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement("a");
      link.href = url; link.download = `replies-${from}-${to}.csv`; link.click();
      URL.revokeObjectURL(url);
    } catch (err) { toast.error(messageFrom(err)); } finally { setExporting(false); }
  }, [replyParams, from, to, toast]);

  const fmtInt = (n: number) => n.toLocaleString(locale);
  const fmtWhen = (iso: string) => new Date(iso).toLocaleString(locale, { dateStyle: "medium", timeStyle: "short" });
  const dayLabel = (iso: string) => new Date(`${iso}T00:00`).toLocaleDateString(locale, { day: "numeric", month: "short" });
  const duration = (s: number | null) => {
    if (s == null) return "—";
    if (s < 60) return t("reports.ops.seconds", { n: Math.round(s) });
    if (s < 3600) return t("reports.ops.minutes", { n: Math.round(s / 60) });
    return t("reports.ops.hours", { n: (s / 3600).toFixed(1) });
  };
  const channelLabel = (value: string | null) => {
    if (!value) return "—";
    if (value === "playground") return t("inbox.channelPlayground");
    if (value === "whatsapp") return t("inbox.channelWhatsapp");
    if (value === "whatsapp_cloud") return t("inbox.channelWhatsappCloud");
    if (value === "instagram") return t("social.instagram.title");
    if (value === "messenger") return t("social.messenger.title");
    if (value === "widget") return t("inbox.channelWidget");
    return value;
  };
  const agentsForClient = clientId ? (filters?.agents ?? []).filter((a) => a.client_id === clientId) : (filters?.agents ?? []);
  const totalCost = report?.totals.cost_usd ?? 0;
  const estimatedReplies = rows.filter((r) => r.estimated).length;
  const pageCount = Math.max(1, Math.ceil(total / PAGE));

  const costGroupTable = (items: ReportGroup[], head: string, emptyName: string) => (
    <div className="table-shell"><table className="data-table">
      <thead><tr><th>{head}</th><th>{t("reports.cols.replies")}</th><th>{t("reports.cols.tokensIn")}</th><th>{t("reports.cols.tokensOut")}</th><th>{t("reports.cols.cost")}</th><th>{t("reports.cols.share")}</th></tr></thead>
      <tbody>{items.map((item) => (
        <tr key={item.id ?? "none"}>
          <td><strong>{item.id ? item.name || "—" : emptyName}</strong></td>
          <td>{fmtInt(item.replies)}</td><td>{fmtInt(item.input_tokens)}</td><td>{fmtInt(item.output_tokens)}</td>
          <td><strong>{money(item.cost_usd)}</strong></td>
          <td><small className="muted">{totalCost ? Math.round((item.cost_usd / totalCost) * 100) : 0}%</small></td>
        </tr>
      ))}</tbody>
    </table></div>
  );

  const opsGroupTable = (items: OpsGroup[], head: string, label: (g: OpsGroup) => string) => (
    <div className="table-shell"><table className="data-table">
      <thead><tr><th>{head}</th><th>{t("reports.ops.cols.conversations")}</th><th>{t("reports.ops.cols.contacts")}</th><th>{t("reports.ops.cols.aiPct")}</th><th>{t("reports.ops.cols.handoffs")}</th><th>{t("reports.ops.cols.inbound")}</th><th>{t("reports.ops.cols.firstReply")}</th></tr></thead>
      <tbody>{items.map((item) => (
        <tr key={item.id ?? "none"}>
          <td><strong>{label(item)}</strong></td>
          <td>{fmtInt(item.conversations)}</td><td>{fmtInt(item.contacts)}</td>
          <td>{item.ai_resolved_pct}%</td><td>{fmtInt(item.handoffs)}</td><td>{fmtInt(item.inbound)}</td>
          <td>{duration(item.first_reply_s)}</td>
        </tr>
      ))}</tbody>
    </table></div>
  );

  return <div className="page">
    <PageHead eyebrow={t("reports.head.eyebrow")} title={t("reports.head.title")} description={t("reports.head.description")} />

    <div className="tabs">
      <button className={tab === "summary" ? "active" : ""} onClick={() => changeTab("summary")}>{t("reports.tabs.summary")}</button>
      <button className={tab === "costs" ? "active" : ""} onClick={() => changeTab("costs")}>{t("reports.tabs.costs")}</button>
      <button className={tab === "conversations" ? "active" : ""} onClick={() => changeTab("conversations")}>{t("reports.tabs.conversations")}</button>
    </div>

    {tab === "conversations" ? <ConversationExplorer
      basePath="/reports/conversations" scope="agency"
      options={{ clients: filters?.clients ?? [], agents: filters?.agents ?? [], channels: filters?.channels ?? [] }}
    /> : <>
    <ReportControls>
      <ControlsRow>
        <PeriodControl value={String(range)} onChange={(v) => setRange(v === "custom" ? "custom" : Number(v))} max={daysAgoISO(0)}
          custom={{ from: customFrom, to: customTo }} onCustom={(from, to) => { setCustomFrom(from); setCustomTo(to); }}
          presets={RANGES.map((value) => ({ value: String(value), label: value === 7 ? t("reports.filters.range7") : value === 30 ? t("reports.filters.range30") : t("reports.filters.range90") }))} />
        <FilterSelect label={t("reports.cols.client")} value={clientId} onChange={(v) => { setClientId(v); setAgentId(""); }} wide>
          <option value="">{t("reports.filters.allClients")}</option>
          {(filters?.clients ?? []).map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </FilterSelect>
        <FilterSelect label={t("reports.cols.agent")} value={agentId} onChange={setAgentId} wide>
          <option value="">{t("reports.filters.allAgents")}</option>
          {agentsForClient.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
        </FilterSelect>
        {tab === "summary" && <FilterSelect label={t("reports.filters.channel")} value={channel} onChange={setChannel}>
          <option value="">{t("reports.filters.allChannels")}</option>
          {(filters?.channels ?? []).map((c) => <option key={c} value={c}>{channelLabel(c)}</option>)}
        </FilterSelect>}
        {tab === "costs" && <FilterSelect label={t("reports.cols.model")} value={model} onChange={setModel} wide>
          <option value="">{t("reports.filters.allModels")}</option>
          {(filters?.models ?? []).map((m) => <option key={m} value={m}>{m}</option>)}
        </FilterSelect>}
      </ControlsRow>
    </ReportControls>

    {loading ? <p className="muted" style={{ padding: "24px 0" }}>{t("reports.loading")}</p> : tab === "summary" ? (
      !ops ? null : <>
        <section className="metrics-grid">
          <article className="metric-card"><span className="metric-icon violet"><MessageSquareText size={20} /></span><div><small>{t("reports.ops.tiles.conversations")}</small><strong>{fmtInt(ops.totals.conversations)}</strong><p>{t("reports.ops.tiles.conversationsHint")}</p></div></article>
          <article className="metric-card"><span className="metric-icon blue"><Users size={20} /></span><div><small>{t("reports.ops.tiles.contacts")}</small><strong>{fmtInt(ops.totals.contacts)}</strong><p>{t("reports.ops.tiles.contactsHint", { count: fmtInt(ops.totals.new_contacts) })}</p></div></article>
          <article className="metric-card"><span className="metric-icon green"><Bot size={20} /></span><div><small>{t("reports.ops.tiles.aiResolved")}</small><strong>{ops.totals.ai_resolved_pct}%</strong><p>{t("reports.ops.tiles.aiResolvedHint", { done: fmtInt(ops.totals.ai_resolved), total: fmtInt(ops.totals.conversations) })}</p></div></article>
          <article className="metric-card"><span className="metric-icon amber"><UserRound size={20} /></span><div><small>{t("reports.ops.tiles.handoffs")}</small><strong>{fmtInt(ops.totals.handoffs)}</strong><p>{t("reports.ops.tiles.handoffsHint")}</p></div></article>
          <article className="metric-card"><span className="metric-icon blue"><Clock size={20} /></span><div><small>{t("reports.ops.tiles.firstReply")}</small><strong>{duration(ops.totals.first_reply_s)}</strong><p>{t("reports.ops.tiles.firstReplyHint")}</p></div></article>
          <article className="metric-card"><span className="metric-icon violet"><Inbox size={20} /></span><div><small>{t("reports.ops.tiles.open")}</small><strong>{fmtInt(ops.totals.open)}</strong><p>{t("reports.ops.tiles.openHint", { count: fmtInt(ops.totals.unanswered) })}</p></div></article>
          <article className="metric-card"><span className="metric-icon green"><MessageSquareText size={20} /></span><div><small>{t("reports.ops.tiles.inbound")}</small><strong>{fmtInt(ops.totals.inbound)}</strong><p>{t("reports.ops.tiles.inboundHint", { ai: fmtInt(ops.totals.ai_replies), human: fmtInt(ops.totals.human_replies) })}</p></div></article>
          <article className="metric-card"><span className="metric-icon amber"><AlertTriangle size={20} /></span><div><small>{t("reports.ops.tiles.failures")}</small><strong>{fmtInt(ops.totals.delivery_failures)}</strong><p>{t("reports.ops.tiles.failuresHint", { count: fmtInt(ops.totals.tool_errors) })}</p></div></article>
        </section>

        {ops.totals.conversations === 0 ? <EmptyState icon={<MessageSquareText />} title={t("reports.ops.noData")} description={t("reports.emptyBody")} /> : <>
          <section className="section-block">
            <div className="section-heading"><div><h2>{t("reports.ops.overTime")}</h2></div>
              <div className="heading-tools">
                <div className="report-legend">
                  <span><i style={{ background: "var(--purple)" }} /> {t("reports.ops.cols.conversations")}</span>
                  <span><i style={{ background: "var(--amber)" }} /> {t("reports.ops.cols.handoffs")}</span>
                </div>
                <Segmented<(typeof BUCKETS)[number]> value={bucket} onChange={setBucket} options={BUCKETS.map((b) => ({ value: b, label: t(`reports.buckets.${b}`) }))} />
              </div>
            </div>
            <div className="panel" style={{ padding: "18px 16px 12px" }}>
              <TimeChart ariaLabel={t("reports.ops.overTime")} format={fmtInt}
                points={ops.by_period.map((p) => ({ key: p.day, label: dayLabel(p.day), values: [p.conversations, p.handoffs] }))}
                series={[{ name: t("reports.ops.cols.conversations"), color: "var(--purple)" }, { name: t("reports.ops.cols.handoffs"), color: "var(--amber)" }]} />
            </div>
          </section>

          <section className="section-block">
            <div className="section-heading"><div><h2>{t("reports.sections.byClient")}</h2></div></div>
            {opsGroupTable(ops.by_client, t("reports.cols.client"), (g) => g.id ? g.name || "—" : t("reports.noClient"))}
          </section>
          <section className="section-block">
            <div className="section-heading"><div><h2>{t("reports.ops.byChannel")}</h2></div></div>
            {opsGroupTable(ops.by_channel, t("reports.cols.channel"), (g) => channelLabel(g.id))}
          </section>
        </>}
      </>
    ) : (
      !report ? null : <>
        <section className="metrics-grid">
          <article className="metric-card"><span className="metric-icon green"><Coins size={20} /></span><div><small>{t("reports.tiles.cost")}</small><strong>{money(report.totals.cost_usd)}</strong><p>{t("reports.tiles.costHint", { replies: fmtInt(report.totals.replies) })}</p></div></article>
          <article className="metric-card"><span className="metric-icon blue"><Bot size={20} /></span><div><small>{t("reports.tiles.avg")}</small><strong>{money(report.totals.avg_cost_per_reply_usd)}</strong><p>{t("reports.tiles.avgHint", { tokens: fmtInt(report.totals.input_tokens + report.totals.output_tokens) })}</p></div></article>
          <article className="metric-card"><span className="metric-icon violet"><MessageSquareText size={20} /></span><div><small>{t("reports.tiles.conversations")}</small><strong>{fmtInt(report.totals.conversations)}</strong><p>{t("reports.tiles.conversationsHint")}</p></div></article>
          <article className="metric-card"><span className="metric-icon amber"><Sparkles size={20} /></span><div><small>{t("reports.tiles.estimated")}</small><strong>{fmtInt(estimatedReplies)}</strong><p>{t("reports.tiles.estimatedHint")}</p></div></article>
        </section>

        {report.totals.replies === 0 ? <EmptyState icon={<Coins />} title={t("reports.emptyTitle")} description={t("reports.emptyBody")} /> : <>
          <section className="section-block">
            <div className="section-heading"><div><h2>{t("reports.sections.byDay")}</h2></div></div>
            <div className="panel" style={{ padding: "18px 16px 12px" }}>
              <TimeChart ariaLabel={t("reports.sections.byDay")} format={money} axisFormat={(v, d) => `$${v.toFixed(d)}`}
                points={report.by_day.map((day) => ({ key: day.date, label: dayLabel(day.date), values: [day.cost_usd] }))}
                series={[{ name: t("reports.cols.cost"), color: "var(--purple)" }]} />
            </div>
          </section>

          <section className="section-block"><div className="section-heading"><div><h2>{t("reports.sections.byClient")}</h2></div></div>{costGroupTable(report.by_client, t("reports.cols.client"), t("reports.noClient"))}</section>
          <section className="section-block"><div className="section-heading"><div><h2>{t("reports.sections.byAgent")}</h2></div></div>{costGroupTable(report.by_agent, t("reports.cols.agent"), "—")}</section>
          <section className="section-block"><div className="section-heading"><div><h2>{t("reports.sections.byModel")}</h2></div></div>{costGroupTable(report.by_model, t("reports.cols.model"), "—")}</section>

          <section className="section-block">
            <div className="section-heading"><div><h2>{t("reports.sections.replies")}</h2><p>{t("reports.sections.repliesHint")}</p></div></div>
            <div className="report-actions">
              <label className="search-box report-search"><Search size={16} /><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder={t("reports.filters.search")} /></label>
              <button type="button" className="button secondary" onClick={exportCsv} disabled={exporting || rows.length === 0} style={{ marginLeft: "auto" }}>
                {exporting ? <LoaderCircle size={15} className="spin" /> : <Download size={15} />} {t("reports.export")}
              </button>
            </div>
            <div className="table-shell" style={{ overflowX: "auto" }}><table className="data-table" style={{ whiteSpace: "nowrap" }}>
              <thead><tr>
                <th>{t("reports.cols.date")}</th><th>{t("reports.cols.conversation")}</th><th>{t("reports.cols.contact")}</th><th>{t("reports.cols.client")}</th><th>{t("reports.cols.agent")}</th><th>{t("reports.cols.channel")}</th>
                <th>{t("reports.cols.model")}</th><th>{t("reports.cols.servedBy")}</th><th>{t("reports.cols.duration")}</th><th>{t("reports.cols.tokensIn")}</th><th>{t("reports.cols.tokensOut")}</th><th>{t("reports.cols.cost")}</th>
              </tr></thead>
              <tbody>{rows.map((row) => (
                <tr key={row.id}>
                  <td>{fmtWhen(row.created_at)}</td>
                  <td>{row.conversation_id ? <code style={{ fontSize: 12 }}>{row.conversation_id.slice(0, 8)}</code> : "—"}</td>
                  <td>{row.contact_name || (row.conversation_id ? t("reports.unknown") : "—")}</td>
                  <td>{row.client_name || "—"}</td><td>{row.agent_name || "—"}</td><td>{channelLabel(row.channel)}</td>
                  <td>{row.model}</td>
                  <td>{row.served_by || "—"}</td>
                  <td>{row.duration_ms == null ? "—" : `${(row.duration_ms / 1000).toFixed(row.duration_ms < 10_000 ? 1 : 0)} s`}</td>
                  <td>{fmtInt(row.input_tokens)}</td><td>{fmtInt(row.output_tokens)}</td>
                  <td><strong>{money(row.cost_usd)}</strong>{row.estimated && <small className="muted"> · {t("reports.estimatedMark")}</small>}</td>
                </tr>
              ))}</tbody>
            </table></div>
            <div className="report-pager">
              <small className="muted">{t("reports.pageOf", { from: fmtInt(total ? page * PAGE + 1 : 0), to: fmtInt(Math.min(total, (page + 1) * PAGE)), total: fmtInt(total) })}</small>
              <button type="button" className="button secondary" onClick={() => setPage((p) => Math.max(0, p - 1))} disabled={page === 0}>{t("reports.prev")}</button>
              <button type="button" className="button secondary" onClick={() => setPage((p) => Math.min(pageCount - 1, p + 1))} disabled={page >= pageCount - 1}>{t("reports.next")}</button>
            </div>
          </section>
        </>}
      </>
    )}
    </>}
  </div>;
}
