"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { DEFAULT_PAGE_SIZE, pageSlice, TablePager } from "@/components/table-pager";
import { ArrowRight, Bot, Plus, Search } from "lucide-react";
import { api } from "@/lib/api";
import { useLanguage } from "@/lib/i18n";
import { businessLabel, useIndustries } from "@/lib/industries";
import { EmptyState, PageHead, StatusBadge } from "@/components/ui";
import { TableSkeleton } from "@/components/skeleton";
import { modelLabel } from "@/lib/providers";
import type { Agent, Client } from "@/types";

export default function AgentsPage() {
  const { t, lang } = useLanguage();
  const catalog = useIndustries();
  const [agents, setAgents] = useState<Agent[]>([]);
  const [clients, setClients] = useState<Client[]>([]);
  const [clientId, setClientId] = useState("");
  const [search, setSearch] = useState("");
  const [loaded, setLoaded] = useState(false);
  useEffect(() => { Promise.all([api<Agent[]>("/agents"), api<Client[]>("/clients")]).then(([a, c]) => { setAgents(a); setClients(c); }).catch(() => {}).finally(() => setLoaded(true)); }, []);
  const visible = useMemo(() => agents.filter((agent) => (!clientId || agent.client_id === clientId) && `${agent.name} ${agent.client.name}`.toLowerCase().includes(search.toLowerCase())), [agents, clientId, search]);
  // Paged in the browser; a new filter starts over from the first page.
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
  useEffect(() => { setPage(0); }, [clientId, search, pageSize]);
  const rows = pageSlice(visible, page, pageSize);
  return <div className="page"><PageHead eyebrow={t("agents.list.eyebrow")} title={t("agents.list.title")} description={t("agents.list.description")} action={<Link href="/agents/new" className="button primary"><Plus size={18} /> {t("agents.list.newAgent")}</Link>} />
    <div className="toolbar filters"><label className="search-box"><Search size={18} /><input value={search} onChange={(e) => setSearch(e.target.value)} placeholder={t("agents.list.searchPlaceholder")} /></label><label className="filter-select">{t("agents.list.clientLabel")}<select value={clientId} onChange={(e) => setClientId(e.target.value)}><option value="">{t("agents.list.allClients")}</option>{clients.map((client) => <option value={client.id} key={client.id}>{client.name}</option>)}</select></label></div>
    {!loaded ? <TableSkeleton columns={5} /> : visible.length ? <div className="table-shell"><table className="data-table"><thead><tr><th>{t("agents.list.thAgent")}</th><th>{t("agents.list.thClient")}</th><th>{t("agents.list.thModel")}</th><th>{t("agents.list.thStatus")}</th><th /></tr></thead><tbody>{rows.map((agent) => <tr key={agent.id}><td><Link href={`/agents/${agent.id}`} className="entity-cell"><span className="agent-avatar"><Bot size={18} /></span><span><strong>{agent.name}</strong><small>{businessLabel(catalog, agent.client, lang)}</small></span></Link></td><td><Link href={`/clients/${agent.client_id}`} className="table-link">{agent.client.name}</Link></td><td>{agent.model ? <span className="entity-cell"><strong>{modelLabel(agent.model)}</strong><small>{agent.model}</small></span> : <span className="muted">{t("agents.list.notConfigured")}</span>}</td><td><StatusBadge active={agent.is_active} /></td><td><Link href={`/agents/${agent.id}`} className="row-arrow"><ArrowRight size={17} /></Link></td></tr>)}</tbody></table><TablePager label={t("agents.list.count", { count: visible.length })} total={visible.length} page={page} pageSize={pageSize} onPage={setPage} onPageSize={setPageSize} /></div> : <EmptyState icon={<Bot />} title={t("agents.list.emptyTitle")} description={clients.length ? t("agents.list.emptyWithClients") : t("agents.list.emptyNoClients")} action={<Link href={clients.length ? "/agents/new" : "/clients/new"} className="button primary">{t("agents.list.continue")}</Link>} />}
  </div>;
}
