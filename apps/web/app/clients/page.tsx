"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { ArrowRight, Building2, Plus, Search } from "lucide-react";
import { api } from "@/lib/api";
import { useT } from "@/lib/i18n";
import { EmptyState, PageHead, StatusBadge } from "@/components/ui";
import { TableSkeleton } from "@/components/skeleton";
import type { Client } from "@/types";

export default function ClientsPage() {
  const t = useT();
  const [clients, setClients] = useState<Client[]>([]);
  const [search, setSearch] = useState("");
  const [loaded, setLoaded] = useState(false);
  useEffect(() => { api<Client[]>("/clients").then(setClients).catch(() => {}).finally(() => setLoaded(true)); }, []);
  const visible = useMemo(() => clients.filter((item) => `${item.name} ${item.industry}`.toLowerCase().includes(search.toLowerCase())), [clients, search]);

  return <div className="page">
    <PageHead eyebrow={t("clients.list.eyebrow")} title={t("clients.list.title")} description={t("clients.list.description")} action={<Link href="/clients/new" className="button primary"><Plus size={18} /> {t("clients.list.newClient")}</Link>} />
    <div className="toolbar"><label className="search-box"><Search size={18} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder={t("clients.list.searchPlaceholder")} /></label></div>
    {!loaded ? <TableSkeleton columns={6} /> : visible.length ? <div className="table-shell"><table className="data-table"><thead><tr><th>{t("clients.list.colClient")}</th><th>{t("clients.list.colIndustry")}</th><th>{t("clients.list.colAgents")}</th><th>{t("clients.list.colPortal")}</th><th>{t("clients.list.colStatus")}</th><th /></tr></thead><tbody>{visible.map((client) => <tr key={client.id}><td><Link href={`/clients/${client.id}`} className="entity-cell"><span className="entity-avatar">{client.name.slice(0, 2).toUpperCase()}</span><span><strong>{client.name}</strong><small>{client.description || t("clients.list.noDescription")}</small></span></Link></td><td>{client.industry || t("clients.list.industryUndefined")}</td><td>{client.agents.length}</td><td><span className={client.portal_enabled ? "pill purple" : "pill"}>{client.portal_enabled ? t("clients.list.portalPublished") : t("clients.list.portalUnpublished")}</span></td><td><StatusBadge active={client.is_active} /></td><td><Link href={`/clients/${client.id}`} className="row-arrow" aria-label={t("clients.list.openAria", { name: client.name })}><ArrowRight size={17} /></Link></td></tr>)}</tbody></table></div> : <EmptyState icon={<Building2 />} title={search ? t("clients.list.emptyNoMatchTitle") : t("clients.list.emptyCreateTitle")} description={search ? t("clients.list.emptyNoMatchDescription") : t("clients.list.emptyCreateDescription")} action={!search && <Link href="/clients/new" className="button primary"><Plus size={18} /> {t("clients.list.createClient")}</Link>} />}
  </div>;
}
