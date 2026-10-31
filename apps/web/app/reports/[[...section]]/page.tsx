"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle, Bot, Clock, Coins, Download, Inbox, LoaderCircle, MessageSquareText, Search, Sparkles, UserRound, Users } from "lucide-react";
import { EmptyState, PageHead } from "@/components/ui";
import { ConversationExplorer } from "@/components/reports/conversation-explorer";
import { ControlsRow, FilterSelect, PeriodControl, ReportControls, Segmented } from "@/components/reports/filter-bar";
import { TimeChart } from "@/components/reports/time-chart";
import { DEFAULT_PAGE_SIZE, PAGE_SIZES, TablePager } from "@/components/table-pager";
import { SortHeader, useTableView, type Sort } from "@/components/table-sort";
import { useToast } from "@/components/toast";
import { currentSections, showSections } from "@/lib/section-path";
import { api, apiUrl, messageFrom } from "@/lib/api";
import { useLanguage } from "@/lib/i18n";
import type { CostReport, Operations, OpsGroup, ReportFilters, ReportGroup, ReportReply } from "@/types";

const RANGES = [7, 30, 90] as const;
const BUCKETS = ["day", "week", "month", "year"] as const;
const REFRESH_MS = 30_000;

type GroupKey = "name" | "replies" | "input_tokens" | "output_tokens" | "cost_usd";
type OpsKey = "name" | "conversations" | "contacts" | "ai_resolved_pct" | "handoffs" | "inbound" | "first_reply_s";
// The reply list is paged by the API, so it is ordered there too (REPLY_SORTS).
type ReplyKey = "created_at" | "contact" | "client" | "agent" | "channel" | "model" | "served_by" | "duration_ms" | "input_tokens" | "output_tokens" | "cost_usd";

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

/** The pager under a table, once the table holds more than one page of the
 * smallest size. */
function Pager({ total, page, pageSize, onPage, onPageSize }: { total: number; page: number; pageSize: number; onPage: (page: number) => void; onPageSize: (size: number) => void }) {
  const { t, lang } = useLanguage();
  if (total <= PAGE_SIZES[0]) return null;
  const fmtInt = (n: number) => n.toLocaleString(lang === "es" ? "es" : "en");
  const label = t("reports.pageOf", { from: fmtInt(page * pageSize + 1), to: fmtInt(Math.min(total, (page + 1) * pageSize)), total: fmtInt(total) });
  return <TablePager label={label} total={total} page={page} pageSize={pageSize} onPage={onPage} onPageSize={onPageSize} />;
}

function CostGroupTable({ items, head, emptyName, totalCost, fmtInt }: { items: ReportGroup[]; head: string; emptyName: string; totalCost: number; fmtInt: (n: number) => string }) {
  const { t } = useLanguage();
  const name = (item: ReportGroup) => item.id ? item.name || "—" : emptyName;
  const view = useTableView<ReportGroup, GroupKey>(items, (item, key) => key === "name" ? name(item) : item[key], { key: "cost_usd", order: "desc" });
  const header = (column: GroupKey, label: string) => <SortHeader column={column} label={label} sort={view.sort} onSort={view.onSort} descending={column !== "name"} />;
  return <div className="table-shell"><table className="data-table">
    <thead><tr>{header("name", head)}{header("replies", t("reports.cols.replies"))}{header("input_tokens", t("reports.cols.tokensIn"))}{header("output_tokens", t("reports.cols.tokensOut"))}{header("cost_usd", t("reports.cols.cost"))}<th>{t("reports.cols.share")}</th></tr></thead>
    <tbody>{view.rows.map((item) => (
      <tr key={item.id ?? "none"}>
        <td><strong>{name(item)}</strong></td>
        <td>{fmtInt(item.replies)}</td><td>{fmtInt(item.input_tokens)}</td><td>{fmtInt(item.output_tokens)}</td>
        <td><strong>{money(item.cost_usd)}</strong></td>
        <td><small className="muted">{totalCost ? Math.round((item.cost_usd / totalCost) * 100) : 0}%</small></td>
      </tr>
    ))}</tbody>
  </table><Pager {...view} /></div>;
}

function OpsGroupTable({ items, head, label, fmtInt, duration }: { items: OpsGroup[]; head: string; label: (g: OpsGroup) => string; fmtInt: (n: number) => string; duration: (s: number | null) => string }) {
  const { t } = useLanguage();
  const view = useTableView<OpsGroup, OpsKey>(items, (item, key) => key === "name" ? label(item) : item[key], { key: "conversations", order: "desc" });
  const header = (column: OpsKey, text: string) => <SortHeader column={column} label={text} sort={view.sort} onSort={view.onSort} descending={column !== "name"} />;
  return <div className="table-shell"><table className="data-table">
    <thead><tr>{header("name", head)}{header("conversations", t("reports.ops.cols.conversations"))}{header("contacts", t("reports.ops.cols.contacts"))}{header("ai_resolved_pct", t("reports.ops.cols.aiPct"))}{header("handoffs", t("reports.ops.cols.handoffs"))}{header("inbound", t("reports.ops.cols.inbound"))}{header("first_reply_s", t("reports.ops.cols.firstReply"))}</tr></thead>
    <tbody>{view.rows.map((item) => (
      <tr key={item.id ?? "none"}>
        <td><strong>{label(item)}</strong></td>
        <td>{fmtInt(item.conversations)}</td><td>{fmtInt(item.contacts)}</td>
        <td>{item.ai_resolved_pct}%</td><td>{fmtInt(item.handoffs)}</td><td>{fmtInt(item.inbound)}</td>
        <td>{duration(item.first_reply_s)}</td>
      </tr>
    ))}</tbody>
  </table><Pager {...view} /></div>;
}

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
  const [pageSize, setPageSize] = useState<number>(DEFAULT_PAGE_SIZE);
  const [replySort, setReplySort] = useState<Sort<ReplyKey>>({ key: "created_at", order: "desc" });
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
    // The export keeps the order on screen.
    p.set("sort", replySort.key);
    p.set("order", replySort.order);
    return p;
  }, [scope, model, query, replySort]);

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
        api<{ items: ReportReply[]; total: number }>(`/reports/replies?${replyParams}&limit=${pageSize}&offset=${page * pageSize}`),
      ]);
      setReport(summary);
      setRows(replies.items);
      setTotal(replies.total);
    }
  }, [tab, from, to, scope, channel, bucket, model, replyParams, page, pageSize]);

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
  const costGroupTable = (items: ReportGroup[], head: string, emptyName: string) =>
    <CostGroupTable items={items} head={head} emptyName={emptyName} totalCost={totalCost} fmtInt={fmtInt} />;
  const opsGroupTable = (items: OpsGroup[], head: string, label: (g: OpsGroup) => string) =>
    <OpsGroupTable items={items} head={head} label={label} fmtInt={fmtInt} duration={duration} />;
  const replyHeader = (column: ReplyKey, label: string, descending = false) =>
    <SortHeader column={column} label={label} sort={replySort} onSort={setReplySort} descending={descending} />;

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
          <article className="metric-card"><span className="metric-icon amber"><Sparkles size={20} /></span><div><small>{t("reports.tiles.estimated")}</small><strong>{fmtInt(report.totals.estimated_replies ?? 0)}</strong><p>{t("reports.tiles.estimatedHint")}</p></div></article>
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
            <div className="table-shell"><div style={{ overflowX: "auto" }}><table className="data-table" style={{ whiteSpace: "nowrap" }}>
              <thead><tr>
                {replyHeader("created_at", t("reports.cols.date"), true)}<th>{t("reports.cols.conversation")}</th>{replyHeader("contact", t("reports.cols.contact"))}{replyHeader("client", t("reports.cols.client"))}{replyHeader("agent", t("reports.cols.agent"))}{replyHeader("channel", t("reports.cols.channel"))}
                {replyHeader("model", t("reports.cols.model"))}{replyHeader("served_by", t("reports.cols.servedBy"))}{replyHeader("duration_ms", t("reports.cols.duration"), true)}{replyHeader("input_tokens", t("reports.cols.tokensIn"), true)}{replyHeader("output_tokens", t("reports.cols.tokensOut"), true)}{replyHeader("cost_usd", t("reports.cols.cost"), true)}
              </tr></thead>
              <tbody>{rows.map((row) => (
                <tr key={row.id}>
                  <td>{fmtWhen(row.created_at)}</td>
                  <td>{row.conversation_id ? <code style={{ fontSize: 12 }}>{row.conversation_id.slice(0, 8)}</code> : "—"}</td>
                  <td>{row.contact_name || (row.conversation_id ? t("reports.unknown") : "—")}</td>
                  <td>{row.client_name || "—"}</td><td>{row.agent_name || "—"}</td><td>{channelLabel(row.channel)}</td>
                  <td>{row.model}{row.purpose === "summary" && <> <span className="pill">{t("reports.cols.purposeSummary")}</span></>}{row.purpose === "call" && <> <span className="pill">{t("reports.cols.purposeCall")}</span></>}</td>
                  <td>{row.served_by || "—"}</td>
                  <td>{row.duration_ms == null ? "—" : `${(row.duration_ms / 1000).toFixed(row.duration_ms < 10_000 ? 1 : 0)} s`}</td>
                  <td>{fmtInt(row.input_tokens)}</td><td>{fmtInt(row.output_tokens)}</td>
                  <td><strong>{money(row.cost_usd)}</strong>{row.estimated && <small className="muted"> · {t("reports.estimatedMark")}</small>}</td>
                </tr>
              ))}</tbody>
            </table></div><Pager total={total} page={page} pageSize={pageSize} onPage={setPage} onPageSize={(size) => { setPageSize(size); setPage(0); }} /></div>
          </section>
        </>}
      </>
    )}
    </>}
  </div>;
}
