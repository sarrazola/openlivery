"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowRight, Bot, Building2, Cpu, MessagesSquare, MessageSquareText, Radio, UserRound } from "lucide-react";
import { api } from "@/lib/api";
import { useLanguage } from "@/lib/i18n";
import { businessLabel, useIndustries } from "@/lib/industries";
import { PageHead, StatusBadge } from "@/components/ui";
import { ListRowsSkeleton, PanelSkeleton, Skeleton } from "@/components/skeleton";
import type { Agent, AgentSummary, Conversation } from "@/types";

type Dashboard = { clients: number; active_clients: number; agents: number; active_agents: number; conversations: number; channels: number; connected_channels: number; recent_agents: AgentSummary[] };
type DailyPoint = { date: string; count: number };
type TopAgent = { id: string; name: string; conversations: number };
type ModelUsage = { model: string; input_tokens: number; output_tokens: number };
type Metrics = { messages: number; human_conversations: number; by_channel: Record<string, number>; daily_conversations: DailyPoint[]; top_agents: TopAgent[]; tokens_in: number; tokens_out: number; usage_by_model: ModelUsage[] };

export default function HomePage() {
  const { t, lang } = useLanguage();
  const catalog = useIndustries();
  const [data, setData] = useState<Dashboard | null>(null);
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [range, setRange] = useState(14);
  const [loadedCore, setLoadedCore] = useState(false);
  const [loadedMetrics, setLoadedMetrics] = useState(false);
  useEffect(() => { Promise.all([api<Dashboard>("/dashboard"), api<Agent[]>("/agents"), api<Conversation[]>("/conversations")]).then(([d, a, x]) => { setData(d); setAgents(a); setConversations(x); }).catch(() => {}).finally(() => setLoadedCore(true)); }, []);
  useEffect(() => { setLoadedMetrics(false); api<Metrics>(`/dashboard/metrics?days=${range}`).then(setMetrics).catch(() => {}).finally(() => setLoadedMetrics(true)); }, [range]);

  const maxDaily = Math.max(1, ...(metrics?.daily_conversations.map((p) => p.count) ?? [0]));
  const trend = metrics?.daily_conversations ?? [];
  const usage = metrics?.usage_by_model ?? [];
  const maxUsage = Math.max(1, ...usage.map((u) => u.input_tokens + u.output_tokens));

  return (
    <div className="page">
      <PageHead eyebrow={t("home.head.eyebrow")} title={t("home.head.title")} description={t("home.head.description")} action={<label className="range-select"><select value={range} onChange={(e) => setRange(Number(e.target.value))}>{[7, 14, 30, 90].map((n) => <option key={n} value={n}>{t("home.range.days", { count: n })}</option>)}</select></label>} />
      <section className="panel next-steps home-next-steps">
        <div className="panel-head"><div><h3>{t("home.nextSteps.title")}</h3><p>{t("home.nextSteps.subtitle")}</p></div></div>
        <ol><li className={loadedCore && data?.clients ? "done" : ""}>{loadedCore ? <span>{data?.clients ? "✓" : "1"}</span> : <span><Skeleton style={{ width: 18, height: 18, borderRadius: 999 }} /></span>}<div><strong>{t("home.nextSteps.step1Title")}</strong><small>{t("home.nextSteps.step1Desc")}</small></div></li><li className={loadedCore && data?.agents ? "done" : ""}>{loadedCore ? <span>{data?.agents ? "✓" : "2"}</span> : <span><Skeleton style={{ width: 18, height: 18, borderRadius: 999 }} /></span>}<div><strong>{t("home.nextSteps.step2Title")}</strong><small>{t("home.nextSteps.step2Desc")}</small></div></li><li><span>3</span><div><strong>{t("home.nextSteps.step3Title")}</strong><small>{t("home.nextSteps.step3Desc")}</small></div></li></ol>
      </section>
      <section className="metrics-grid">
        <article className="metric-card"><span className="metric-icon blue"><Building2 size={20} /></span><div><small>{t("home.metrics.clients")}</small><strong>{loadedCore ? data?.clients ?? "—" : <Skeleton className="sk-line" style={{ width: 52, height: 28 }} />}</strong><p>{t("home.metrics.clientsActive", { count: data?.active_clients ?? 0 })}</p></div></article>
        <article className="metric-card"><span className="metric-icon violet"><Bot size={20} /></span><div><small>{t("home.metrics.agents")}</small><strong>{loadedCore ? agents.length || data?.agents || "—" : <Skeleton className="sk-line" style={{ width: 52, height: 28 }} />}</strong><p>{t("home.metrics.agentsActive", { count: agents.filter((item) => item.is_active).length })}</p></div></article>
        <article className="metric-card"><span className="metric-icon green"><MessageSquareText size={20} /></span><div><small>{t("home.metrics.conversations")}</small><strong>{loadedCore ? conversations.length : <Skeleton className="sk-line" style={{ width: 52, height: 28 }} />}</strong><p>{t("home.metrics.conversationsCaption")}</p></div></article>
        <article className="metric-card"><span className="metric-icon amber"><Radio size={20} /></span><div><small>{t("home.metrics.channels")}</small><strong>{loadedCore ? data?.channels ?? "—" : <Skeleton className="sk-line" style={{ width: 52, height: 28 }} />}</strong><p>{t("home.metrics.channelsConnected", { count: data?.connected_channels ?? 0 })}</p></div></article>
      </section>
      <section className="dashboard-row">
        <div className="panel trend-panel">
          <div className="panel-head"><div><h3>{t("home.activity.title")}</h3><p>{t("home.activity.subtitle", { count: range })}</p></div>
            <div className="trend-stats"><span><MessagesSquare size={14} /> {metrics?.messages ?? 0} · {t("home.activity.messages")}</span><span><UserRound size={14} /> {metrics?.human_conversations ?? 0} · {t("home.activity.humanHandled")}</span></div>
          </div>
          {!loadedMetrics ? <PanelSkeleton rows={3} slim /> : trend.some((p) => p.count > 0) ? <>
            <div className="trend-chart">{trend.map((p) => <div key={p.date} className="trend-col" title={`${p.date}: ${p.count}`}><div className="trend-bar" style={{ height: `${Math.round((p.count / maxDaily) * 100)}%` }} /></div>)}</div>
            <div className="trend-legend"><span>{new Date(`${trend[0].date}T00:00:00`).toLocaleDateString("es", { day: "numeric", month: "short" })}</span><span>{new Date(`${trend[trend.length - 1].date}T00:00:00`).toLocaleDateString("es", { day: "numeric", month: "short" })}</span></div>
          </> : <div className="inline-empty slim"><MessagesSquare size={22} /><div><strong>{t("home.activity.empty")}</strong></div></div>}
        </div>
        <div className="panel">
          <div className="panel-head"><div><h3>{t("home.topAgents.title")}</h3><p>{t("home.topAgents.subtitle")}</p></div></div>
          {!loadedMetrics ? <PanelSkeleton rows={3} /> : metrics?.top_agents.length ? <div className="rank-list">{metrics.top_agents.map((agent, index) => <Link href={`/agents/${agent.id}`} key={agent.id} className="rank-row"><span className="rank-num">{index + 1}</span><span className="agent-avatar"><Bot size={16} /></span><strong>{agent.name}</strong><span className="rank-count">{t("home.topAgents.conversations", { count: agent.conversations })}</span></Link>)}</div> : <div className="inline-empty slim"><Bot size={22} /><div><strong>{t("home.topAgents.empty")}</strong></div></div>}
        </div>
      </section>
      <section className="panel">
        <div className="panel-head"><div><h3>{t("home.usage.title")}</h3><p>{t("home.usage.subtitle")}</p></div>
          <div className="trend-stats"><span>↓ {(metrics?.tokens_in ?? 0).toLocaleString("es")} {t("home.usage.in")}</span><span>↑ {(metrics?.tokens_out ?? 0).toLocaleString("es")} {t("home.usage.out")}</span></div>
        </div>
        {!loadedMetrics ? <PanelSkeleton rows={3} /> : usage.length ? <div className="usage-list">{usage.map((item) => { const total = item.input_tokens + item.output_tokens; return <div className="usage-row" key={item.model}><strong>{item.model}</strong><div className="usage-track"><div className="usage-fill" style={{ width: `${Math.round((total / maxUsage) * 100)}%` }} /></div><span className="usage-count">{total.toLocaleString("es")} tok</span></div>; })}</div> : <div className="inline-empty slim"><Cpu size={22} /><div><strong>{t("home.usage.empty")}</strong></div></div>}
      </section>
      <section className="panel">
        <div className="panel-head"><div><h3>{t("home.recentAgents.title")}</h3><p>{t("home.recentAgents.subtitle")}</p></div><Link href="/agents" className="text-link">{t("home.recentAgents.viewAll")} <ArrowRight size={15} /></Link></div>
        {!loadedCore ? <ListRowsSkeleton rows={4} /> : agents.length ? <div className="compact-list">{agents.slice(0, 5).map((agent) => <Link href={`/agents/${agent.id}`} key={agent.id} className="compact-row"><span className="agent-avatar"><Bot size={18} /></span><div><strong>{agent.name}</strong><small>{agent.client.name}{businessLabel(catalog, agent.client, lang) ? ` · ${businessLabel(catalog, agent.client, lang)}` : ""}</small></div><StatusBadge active={agent.is_active} /><ArrowRight size={16} /></Link>)}</div> : <div className="inline-empty"><Bot size={24} /><div><strong>{t("home.recentAgents.emptyTitle")}</strong><span>{t("home.recentAgents.emptyDesc")}</span></div></div>}
      </section>
    </div>
  );
}
