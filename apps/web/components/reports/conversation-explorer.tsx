"use client";

// The conversation list behind the reports: one row per conversation, the
// columns a person picks, and filters on when it started, its state and who
// handled it. The referral a Meta ad attached to the first message is shown
// as its own column group, not filtered on. Shared by the agency reports
// page and the client portal; the parent says which selectors it has
// options for.

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Columns3, Download, LoaderCircle, Megaphone, MessageSquareText, Search } from "lucide-react";
import { Alert, EmptyState } from "@/components/ui";
import { ControlsRow, FilterSelect, PeriodControl, ReportControls } from "@/components/reports/filter-bar";
import { api, apiUrl, messageFrom } from "@/lib/api";
import { useLanguage } from "@/lib/i18n";
import type { I18nKey } from "@/lib/i18n";
import type { ConversationReportPage, ConversationReportRow } from "@/types";

const PAGE = 50;
const SEARCH_DELAY_MS = 350;
const COLUMNS = [
  "started", "contact", "phone", "client", "agent", "channel", "status", "mode", "assignee", "team",
  "firstReply", "resolution", "inbound", "aiReplies", "humanReplies", "lastMessage",
  "adSourceType", "adHeadline", "adSourceId", "adSourceUrl", "adBody", "adMediaType",
] as const;
type ColumnKey = (typeof COLUMNS)[number];
type Range = "today" | "7" | "30" | "custom";

const AD_COLUMNS: ColumnKey[] = ["adSourceType", "adHeadline", "adSourceId", "adSourceUrl", "adBody", "adMediaType"];
const DEFAULT_COLUMNS: Record<"agency" | "portal", ColumnKey[]> = {
  agency: ["started", "contact", "client", "channel", "status", "assignee", "firstReply", "resolution"],
  portal: ["started", "contact", "channel", "status", "assignee", "firstReply", "resolution"],
};
// The columns that only mean something on one side.
const AGENCY_ONLY: ColumnKey[] = ["client", "agent"];
const PORTAL_ONLY: ColumnKey[] = ["team"];

export type ExplorerOptions = {
  clients?: { id: string; name: string }[];
  agents?: { id: string; name: string; client_id?: string }[];
  channels: string[];
  members?: { id: string; name: string; email?: string }[];
  teams?: { id: string; name: string }[];
};

function localISO(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
function daysAgoISO(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() - days);
  return localISO(d);
}
function clip(value: string, max = 48): string {
  return value.length > max ? `${value.slice(0, max - 1)}…` : value;
}

function readColumns(key: string, fallback: ColumnKey[]): ColumnKey[] {
  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) return fallback;
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return fallback;
    const known = parsed.filter((c): c is ColumnKey => (COLUMNS as readonly string[]).includes(c));
    return known.length ? known : fallback;
  } catch { return fallback; }
}

export function ConversationExplorer({ basePath, scope, options, onOpen }: {
  basePath: string;
  scope: "agency" | "portal";
  options: ExplorerOptions;
  onOpen?: (row: ConversationReportRow) => void;
}) {
  const { t, lang } = useLanguage();
  const locale = lang === "es" ? "es" : "en";
  const storageKey = `openlivery.reports.columns.${scope}`;
  const allowed = useMemo(() => COLUMNS.filter((c) => (scope === "agency" ? !PORTAL_ONLY.includes(c) : !AGENCY_ONLY.includes(c))), [scope]);

  const [range, setRange] = useState<Range>("7");
  const [customFrom, setCustomFrom] = useState(daysAgoISO(6));
  const [customTo, setCustomTo] = useState(daysAgoISO(0));
  const [status, setStatus] = useState("");
  const [mode, setMode] = useState("");
  const [channel, setChannel] = useState("");
  const [clientId, setClientId] = useState("");
  const [agentId, setAgentId] = useState("");
  const [assigneeId, setAssigneeId] = useState("");
  const [teamId, setTeamId] = useState("");
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(0);
  const [columns, setColumns] = useState<ColumnKey[]>(DEFAULT_COLUMNS[scope]);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [data, setData] = useState<ConversationReportPage | null>(null);
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState("");
  const pickerRef = useRef<HTMLDivElement | null>(null);

  // Column choice is the viewer's, kept in this browser only.
  useEffect(() => { setColumns(readColumns(storageKey, DEFAULT_COLUMNS[scope])); }, [storageKey, scope]);
  const saveColumns = (next: ColumnKey[]) => {
    setColumns(next);
    try { window.localStorage.setItem(storageKey, JSON.stringify(next)); } catch { /* per-viewer convenience only */ }
  };
  useEffect(() => {
    if (!pickerOpen) return;
    const close = (event: MouseEvent) => { if (pickerRef.current && !pickerRef.current.contains(event.target as Node)) setPickerOpen(false); };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [pickerOpen]);
  useEffect(() => {
    const timer = setTimeout(() => setQuery(search.trim()), SEARCH_DELAY_MS);
    return () => clearTimeout(timer);
  }, [search]);

  const from = range === "custom" ? customFrom : range === "today" ? daysAgoISO(0) : daysAgoISO(Number(range) - 1);
  const to = range === "custom" ? customTo : daysAgoISO(0);
  const tz = useMemo(() => Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC", []);

  const params = useMemo(() => {
    const p = new URLSearchParams({ from, to, tz });
    if (status) p.set("status", status);
    if (mode) p.set("mode", mode);
    if (channel) p.set("channel", channel);
    if (clientId) p.set("client_id", clientId);
    if (agentId) p.set("agent_id", agentId);
    if (assigneeId) p.set("assignee_id", assigneeId);
    if (teamId) p.set("team_id", teamId);
    if (query) p.set("q", query);
    return p;
  }, [from, to, tz, status, mode, channel, clientId, agentId, assigneeId, teamId, query]);

  useEffect(() => { setPage(0); }, [params]);

  const load = useCallback(async () => {
    if (!from || !to || from > to) return;
    setData(await api<ConversationReportPage>(`${basePath}?${params}&limit=${PAGE}&offset=${page * PAGE}`));
  }, [basePath, params, page, from, to]);
  useEffect(() => {
    let cancelled = false;
    setLoading(true); setError("");
    load().catch((err) => { if (!cancelled) setError(messageFrom(err)); }).finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [load]);

  const exportCsv = useCallback(async () => {
    setExporting(true);
    try {
      const response = await fetch(apiUrl(`${basePath}?${params}&format=csv`), { credentials: "include" });
      if (!response.ok) throw new Error("Export failed");
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement("a");
      link.href = url; link.download = `conversations-${from}-${to}.csv`; link.click();
      URL.revokeObjectURL(url);
    } catch (err) { setError(messageFrom(err)); } finally { setExporting(false); }
  }, [basePath, params, from, to]);

  const none = "-";
  const fmtInt = (n: number) => n.toLocaleString(locale);
  const fmtWhen = (iso: string | null | undefined) => iso ? new Date(iso).toLocaleString(locale, { dateStyle: "medium", timeStyle: "short" }) : none;
  const duration = (s: number | null | undefined) => {
    if (s == null) return none;
    if (s < 60) return t("reports.ops.seconds", { n: Math.round(s) });
    if (s < 3600) return t("reports.ops.minutes", { n: Math.round(s / 60) });
    return t("reports.ops.hours", { n: (s / 3600).toFixed(1) });
  };
  const channelLabel = (value: string | null) => {
    if (!value) return none;
    if (value === "playground") return t("inbox.channelPlayground");
    if (value === "whatsapp") return t("inbox.channelWhatsapp");
    if (value === "whatsapp_cloud") return t("inbox.channelWhatsappCloud");
    if (value === "instagram") return t("social.instagram.title");
    if (value === "messenger") return t("social.messenger.title");
    if (value === "widget") return t("inbox.channelWidget");
    return value;
  };
  const sourceLabel = (value: string | undefined) => value === "ad" ? t("reports.explorer.sourceAd") : value === "post" ? t("reports.explorer.sourcePost") : value || none;
  const colLabel = (key: ColumnKey) => t(`reports.explorer.cols.${key}` as I18nKey);
  const isAd = (key: ColumnKey) => AD_COLUMNS.includes(key);

  const cell = (row: ConversationReportRow, key: ColumnKey) => {
    const acq = row.acquisition ?? {};
    switch (key) {
      case "started": return fmtWhen(row.created_at);
      case "contact": return <strong>{row.contact_name || t("reports.unknown")}</strong>;
      case "phone": return row.contact_phone || none;
      case "client": return row.client_name || none;
      case "agent": return row.agent_name || none;
      case "channel": return channelLabel(row.channel);
      case "status": return <span className={`pill ${row.status === "open" ? "purple" : ""}`}>{row.status === "open" ? t("reports.explorer.open") : t("reports.explorer.resolved")}</span>;
      case "mode": return row.mode === "human" ? t("reports.explorer.modeHuman") : t("reports.explorer.modeAi");
      case "assignee": return row.assignee_name || none;
      case "team": return row.team_name || none;
      case "firstReply": return duration(row.first_reply_s);
      case "resolution": return duration(row.resolution_s);
      case "inbound": return fmtInt(row.inbound);
      case "aiReplies": return fmtInt(row.ai_replies);
      case "humanReplies": return fmtInt(row.human_replies);
      case "lastMessage": return fmtWhen(row.last_message_at);
      case "adSourceType": return acq.source_type ? <span className="pill green"><Megaphone size={11} /> {sourceLabel(acq.source_type)}</span> : none;
      case "adHeadline": return acq.headline ? <span title={acq.headline}>{clip(acq.headline, 60)}</span> : none;
      case "adSourceId": return acq.source_id ? <code style={{ fontSize: 12 }}>{acq.source_id}</code> : none;
      case "adSourceUrl": return acq.source_url ? <a href={acq.source_url} target="_blank" rel="noreferrer" title={acq.source_url}>{clip(acq.source_url, 40)}</a> : none;
      case "adBody": return acq.body ? <span title={acq.body}>{clip(acq.body, 60)}</span> : none;
      case "adMediaType": return acq.media_type || none;
    }
  };

  const agentsForClient = clientId ? (options.agents ?? []).filter((a) => !a.client_id || a.client_id === clientId) : (options.agents ?? []);
  const total = data?.total ?? 0;
  const pageCount = Math.max(1, Math.ceil(total / PAGE));
  const visible = columns.filter((c) => allowed.includes(c));
  const pickerGroup = (keys: ColumnKey[]) => keys.map((key) => <label key={key}>
    <input type="checkbox" checked={visible.includes(key)} onChange={(e) => saveColumns(e.target.checked ? allowed.filter((c) => c === key || visible.includes(c)) : visible.filter((c) => c !== key))} />
    <span>{colLabel(key)}</span>
  </label>);

  return <div className="conversation-explorer">
    <ReportControls>
      <ControlsRow>
        <PeriodControl value={range} onChange={(v) => setRange(v as Range)} max={daysAgoISO(0)}
          custom={{ from: customFrom, to: customTo }} onCustom={(from, to) => { setCustomFrom(from); setCustomTo(to); }}
          presets={[
            { value: "today", label: t("reports.explorer.today") },
            { value: "7", label: t("reports.filters.range7") },
            { value: "30", label: t("reports.filters.range30") },
          ]} />
        <FilterSelect label={t("reports.explorer.status")} value={status} onChange={setStatus}>
          <option value="">{t("reports.explorer.statusAll")}</option>
          <option value="open">{t("reports.explorer.open")}</option>
          <option value="resolved">{t("reports.explorer.resolved")}</option>
        </FilterSelect>
        <FilterSelect label={t("reports.explorer.mode")} value={mode} onChange={setMode}>
          <option value="">{t("reports.explorer.modeAll")}</option>
          <option value="ai">{t("reports.explorer.modeAi")}</option>
          <option value="human">{t("reports.explorer.modeHuman")}</option>
        </FilterSelect>
        <FilterSelect label={t("reports.filters.channel")} value={channel} onChange={setChannel}>
          <option value="">{t("reports.filters.allChannels")}</option>
          {options.channels.map((c) => <option key={c} value={c}>{channelLabel(c)}</option>)}
        </FilterSelect>
        {options.clients && <FilterSelect label={t("reports.cols.client")} value={clientId} onChange={(v) => { setClientId(v); setAgentId(""); }} wide>
          <option value="">{t("reports.filters.allClients")}</option>
          {options.clients.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </FilterSelect>}
        {options.agents && <FilterSelect label={t("reports.cols.agent")} value={agentId} onChange={setAgentId} wide>
          <option value="">{t("reports.filters.allAgents")}</option>
          {agentsForClient.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
        </FilterSelect>}
        {options.members && <FilterSelect label={t("reports.explorer.assignee")} value={assigneeId} onChange={setAssigneeId} wide>
          <option value="">{t("reports.explorer.assigneeAll")}</option>
          {options.members.map((m) => <option key={m.id} value={m.id}>{m.name || m.email}</option>)}
        </FilterSelect>}
        {options.teams && <FilterSelect label={t("reports.explorer.team")} value={teamId} onChange={setTeamId}>
          <option value="">{t("reports.explorer.teamAll")}</option>
          {options.teams.map((team) => <option key={team.id} value={team.id}>{team.name}</option>)}
        </FilterSelect>}
      </ControlsRow>
    </ReportControls>

    <div className="report-actions">
      <label className="search-box"><Search size={16} /><input value={search} onChange={(e) => setSearch(e.target.value)} placeholder={t("reports.explorer.search")} /></label>
      <small className="muted">{loading ? t("reports.loading") : t("reports.pageOf", { from: fmtInt(total ? page * PAGE + 1 : 0), to: fmtInt(Math.min(total, (page + 1) * PAGE)), total: fmtInt(total) })}</small>
      <div className="column-picker" ref={pickerRef}>
        <button type="button" className={`button secondary${pickerOpen ? " active" : ""}`} onClick={() => setPickerOpen((open) => !open)} aria-expanded={pickerOpen}>
          <Columns3 size={15} /> {t("reports.explorer.columns")} ({visible.length})
        </button>
        {pickerOpen && <div className="column-picker-menu" role="group" aria-label={t("reports.explorer.columns")}>
          {pickerGroup(allowed.filter((key) => !isAd(key)))}
          <div className="column-picker-group"><Megaphone size={12} /> {t("reports.explorer.metaAds")}</div>
          {pickerGroup(allowed.filter(isAd))}
          <button type="button" className="link-button" onClick={() => saveColumns(DEFAULT_COLUMNS[scope])}>{t("reports.explorer.columnsReset")}</button>
        </div>}
      </div>
      <button type="button" className="button secondary" onClick={exportCsv} disabled={exporting || total === 0}>
        {exporting ? <LoaderCircle size={15} className="spin" /> : <Download size={15} />} {t("reports.export")}
      </button>
    </div>

    {error && <Alert>{error}</Alert>}
    {!loading && data && data.items.length === 0 ? <EmptyState icon={<MessageSquareText />} title={t("reports.explorer.empty")} description={t("reports.explorer.emptyHint")} /> : (
      <div className="table-shell" style={{ overflowX: "auto" }}><table className="data-table explorer-table" style={{ whiteSpace: "nowrap" }}>
        <thead><tr>
          {visible.map((key) => <th key={key} className={isAd(key) ? "th-ad" : ""}>{isAd(key) && <small>{t("reports.explorer.metaAds")}</small>}{colLabel(key)}</th>)}
          {onOpen && <th aria-label={t("reports.explorer.openRow")} />}
        </tr></thead>
        <tbody>{(data?.items ?? []).map((row) => (
          <tr key={row.id} className={onOpen ? "clickable" : ""} onClick={onOpen ? () => onOpen(row) : undefined}>
            {visible.map((key) => <td key={key} className={isAd(key) ? "td-ad" : ""}>{cell(row, key)}</td>)}
            {onOpen && <td><button type="button" className="link-button" onClick={(e) => { e.stopPropagation(); onOpen(row); }}>{t("reports.explorer.openRow")}</button></td>}
          </tr>
        ))}</tbody>
      </table></div>
    )}

    {total > PAGE && <div className="report-pager">
      <button type="button" className="button secondary" onClick={() => setPage((p) => Math.max(0, p - 1))} disabled={page === 0}>{t("reports.prev")}</button>
      <button type="button" className="button secondary" onClick={() => setPage((p) => Math.min(pageCount - 1, p + 1))} disabled={page >= pageCount - 1}>{t("reports.next")}</button>
    </div>}
  </div>;
}
