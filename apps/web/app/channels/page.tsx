"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowRight, Facebook, Globe2, Instagram, Lock, MessageCircle, QrCode, type LucideIcon } from "lucide-react";
import { PageHead } from "@/components/ui";
import { api } from "@/lib/api";
import { useT } from "@/lib/i18n";
import type { Client } from "@/types";

const futureChannels: { key: "instagram" | "facebook"; icon: LucideIcon; className: string }[] = [
  { key: "instagram", icon: Instagram, className: "instagram" },
  { key: "facebook", icon: Facebook, className: "facebook" },
];

export default function ChannelsPage() {
  const t = useT();
  const [clients, setClients] = useState<Client[]>([]);
  const [clientId, setClientId] = useState("");
  useEffect(() => { api<Client[]>("/clients").then(setClients); }, []);
  const selected = clients.find((item) => item.id === clientId);
  return <div className="page"><PageHead eyebrow={t("channels.head.eyebrow")} title={t("channels.head.title")} description={t("channels.head.description")} />
    <div className="channels-toolbar"><label htmlFor="channel-client">{t("channels.toolbar.clientLabel")}</label><select id="channel-client" value={clientId} onChange={(e) => setClientId(e.target.value)}><option value="">{t("channels.toolbar.allClients")}</option>{clients.map((client) => <option key={client.id} value={client.id}>{client.name}</option>)}</select>{selected && <Link href={`/clients/${selected.id}`} className="button secondary">{t("channels.toolbar.openClient")}</Link>}</div>
    <section className="channel-grid"><article className="channel-card channel-card-live"><div className="channel-icon whatsapp"><MessageCircle size={24} /></div><span className="coming live">{t("channels.whatsappCloud.status")}</span><h3>{t("channels.whatsappCloud.title")}</h3><p>{t("channels.whatsappCloud.description")}</p><small className="channel-owner">{selected?.name || t("channels.whatsappCloud.ownerPlaceholder")}</small>{selected ? <Link className="button primary" href={`/clients/${selected.id}/channels/whatsapp-cloud`}>{t("channels.whatsappCloud.configure")} <ArrowRight size={16} /></Link> : <button className="button disabled" disabled>{t("channels.whatsappCloud.selectClient")}</button>}</article><article className="channel-card channel-card-live"><div className="channel-icon whatsapp"><QrCode size={24} /></div><span className="coming live caution">{t("channels.whatsapp.status")}</span><h3>{t("channels.whatsapp.title")}</h3><p>{t("channels.whatsapp.description")}</p><small className="channel-owner">{selected?.name || t("channels.whatsapp.ownerPlaceholder")}</small>{selected ? <Link className="button primary" href={`/clients/${selected.id}/channels/whatsapp`}>{t("channels.whatsapp.configure")} <ArrowRight size={16} /></Link> : <button className="button disabled" disabled>{t("channels.whatsapp.selectClient")}</button>}</article><article className="channel-card channel-card-live"><div className="channel-icon webchat"><Globe2 size={24} /></div><span className="coming live">{t("channels.webchat.status")}</span><h3>{t("channels.webchat.title")}</h3><p>{t("channels.webchat.description")}</p><small className="channel-owner">{selected?.name || t("channels.webchat.ownerPlaceholder")}</small>{selected ? (selected.agents.length ? <Link className="button primary" href={`/agents/${selected.agents[0].id}?tab=widget`}>{t("channels.webchat.configure")} <ArrowRight size={16} /></Link> : <button className="button disabled" disabled>{t("channels.webchat.needsAgent")}</button>) : <button className="button disabled" disabled>{t("channels.webchat.selectClient")}</button>}</article>{futureChannels.map((channel) => <article className="channel-card" key={channel.key}><div className={`channel-icon ${channel.className}`}><channel.icon size={24} /></div><span className="coming"><Lock size={12} /> {t("channels.future.comingSoon")}</span><h3>{t(`channels.future.${channel.key}.name`)}</h3><p>{t(`channels.future.${channel.key}.description`)}</p><small className="channel-owner">{selected?.name || t("channels.future.ownerPlaceholder")}</small><button className="button disabled" disabled>{t("channels.future.connect")}</button></article>)}</section>
  </div>;
}
