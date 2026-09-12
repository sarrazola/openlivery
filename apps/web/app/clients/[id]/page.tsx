"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft, ArrowRight, Bot, Copy, ExternalLink, FileText, Globe2, ImagePlus, Inbox, LoaderCircle, MessageCircle, Pencil, QrCode, Radio, Save, Settings2, ShieldAlert, ShieldCheck, Trash2, UserCheck, UserRound, Users, UserX } from "lucide-react";
import { Alert, EmptyState, Modal, StatusBadge } from "@/components/ui";
import { IndustryPicker, isBusinessComplete, type IndustryValue } from "@/components/industry-picker";
import { AiHint } from "@/components/ai-hint";
import { Combobox } from "@/components/combobox";
import { TIMEZONES } from "@/lib/timezones";
import { TeamsView } from "@/app/portal/[slug]/teams";
import { TemplatesView } from "@/app/portal/[slug]/templates";
import { FormSkeleton, ListRowsSkeleton } from "@/components/skeleton";
import { useToast } from "@/components/toast";
import { PasswordInput } from "@/components/password-input";
import { ChannelIcon, channelLabel } from "@/lib/channels";
import { SocialReplyNotice, useReplyPolicy } from "@/components/reply-policy";
import { api, ApiError, messageFrom } from "@/lib/api";
import { useLanguage, useT } from "@/lib/i18n";
import { businessLabel, useIndustries } from "@/lib/industries";
import type { Client, ClientDomain, Conversation, PortalRole, PortalUser, SocialChannel, WhatsAppChannel, WhatsAppCloudChannel, WidgetChannel } from "@/types";

type Tab = "details" | "agents" | "channels" | "inbox" | "teams" | "templates" | "portal";
type ChannelKey = "whatsapp_cloud" | "whatsapp" | "webchat" | "instagram" | "messenger";
type ChannelState = "loading" | "off" | "pending" | "connected" | "disconnected";
type ChannelStatus = { state: ChannelState; detail?: string };

function socialState(channel: SocialChannel | null): ChannelStatus {
  if (!channel) return { state: "off" };
  return { state: channel.is_enabled && channel.status === "connected" ? "connected" : "disconnected", detail: channel.username ? `@${channel.username}` : channel.display_name || "" };
}

/** A small dot beside the channel's name: green connected, amber connecting,
 * red disconnected, grey never set up. The words live in the tooltip. */
function ChannelStateBadge({ state }: { state: ChannelState }) {
  const t = useT();
  if (state === "loading") return null;
  const label = state === "connected" ? t("clients.detail.channelConnected") : state === "pending" ? t("clients.detail.channelPending") : state === "disconnected" ? t("clients.detail.channelDisconnected") : t("clients.detail.channelNotConnected");
  return <i className={`channel-state-dot ${state}`} title={label} aria-label={label} role="img" />;
}
type DeletionPreview = { agents: number; channels: number; conversations: number; contacts: number; portal_users: number };

export default function ClientDetailPage() {
  const { t, lang } = useLanguage();
  const toast = useToast();
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const catalog = useIndustries();
  const [client, setClient] = useState<Client | null>(null);
  const [domain, setDomain] = useState<ClientDomain | null>(null);
  const [business, setBusiness] = useState<IndustryValue>({ industry: "", businessType: "", custom: "" });
  const [timezone, setTimezone] = useState("UTC");
  const [tab, setTab] = useState<Tab>("details");
  const [busy, setBusy] = useState(false);
  const [logoVersion, setLogoVersion] = useState(0);
  const logoRef = useRef<HTMLInputElement>(null);
  const load = () => api<Client>(`/clients/${id}`).then((c) => { setClient(c); setBusiness({ industry: c.industry, businessType: c.business_type, custom: c.business_custom }); setTimezone(c.timezone || "UTC"); });
  useEffect(() => { load(); api<ClientDomain>(`/clients/${id}/domain`).then(setDomain); }, [id]);
  // One line per channel: is it connected, and to what. Each channel has its
  // own endpoint and answers 404 when the client never set it up.
  const [channelStates, setChannelStates] = useState<Record<ChannelKey, ChannelStatus> | null>(null);
  useEffect(() => {
    const missing = (err: unknown) => { if (err instanceof ApiError && err.status === 404) return null; throw err; };
    Promise.all([
      api<WhatsAppCloudChannel>(`/whatsapp-cloud/channels/${id}`).catch(missing),
      api<WhatsAppChannel>(`/whatsapp/channels/${id}`).catch(missing),
      api<WidgetChannel>(`/webchat/channels/${id}`).catch(missing),
      api<SocialChannel>(`/social/instagram/channels/${id}`).catch(missing),
      api<SocialChannel>(`/social/messenger/channels/${id}`).catch(missing),
    ]).then(([cloud, qr, widget, instagram, messenger]) => setChannelStates({
      whatsapp_cloud: cloud ? { state: cloud.status === "connected" ? "connected" : "disconnected", detail: cloud.phone_number || cloud.display_name || "" } : { state: "off" },
      whatsapp: qr ? { state: qr.status === "connected" ? "connected" : qr.status === "qr" || qr.status === "connecting" || qr.status === "reconnecting" ? "pending" : "disconnected", detail: qr.phone_number || "" } : { state: "off" },
      webchat: widget ? { state: widget.is_enabled ? "connected" : "disconnected" } : { state: "off" },
      instagram: socialState(instagram),
      messenger: socialState(messenger),
    })).catch(() => {});
  }, [id]);
  const channelState = (key: ChannelKey): ChannelState => channelStates?.[key]?.state ?? "loading";
  const channelDetail = (key: ChannelKey): string => channelStates?.[key]?.detail ?? "";

  async function uploadLogo(file?: File) {
    if (!file) return;
    setBusy(true);
    const data = new FormData(); data.append("file", file);
    try { setClient(await api<Client>(`/clients/${id}/logo`, { method: "POST", body: data })); setLogoVersion((v) => v + 1); toast.success(t("clients.detail.logoUpdated")); }
    catch (err) { toast.error(messageFrom(err)); } finally { setBusy(false); if (logoRef.current) logoRef.current.value = ""; }
  }
  async function deleteLogo() {
    await api(`/clients/${id}/logo`, { method: "DELETE" }); setLogoVersion((v) => v + 1); await load();
  }

  async function saveDetails(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true);
    const data = new FormData(event.currentTarget);
    try { setClient(await api<Client>(`/clients/${id}`, { method: "PATCH", body: JSON.stringify({ name: data.get("name"), industry: business.industry, business_type: business.businessType, business_custom: business.custom, timezone, is_active: data.get("is_active") === "on" }) })); toast.success(t("clients.detail.detailsSaved")); }
    catch (err) { toast.error(messageFrom(err)); } finally { setBusy(false); }
  }

  async function savePortal(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true);
    const data = new FormData(event.currentTarget);
    const payload: Record<string, unknown> = { portal_enabled: data.get("portal_enabled") === "on", portal_slug: data.get("portal_slug"), portal_title: data.get("portal_title") };
    try { setClient(await api<Client>(`/clients/${id}/portal`, { method: "PATCH", body: JSON.stringify(payload) })); toast.success(t("clients.detail.portalUpdated")); }
    catch (err) { toast.error(messageFrom(err)); } finally { setBusy(false); }
  }

  // Deleting takes everything under the client with it, so the dialog shows
  // the counts first and only arms the button once the client's name is typed.
  const [deletePreview, setDeletePreview] = useState<DeletionPreview | null>(null);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleteName, setDeleteName] = useState("");
  const [deleteError, setDeleteError] = useState<string | null>(null);
  async function openDelete() {
    setDeleteName(""); setDeleteError(null); setDeletePreview(null); setDeleteOpen(true);
    try { setDeletePreview(await api<DeletionPreview>(`/clients/${id}/deletion-preview`)); } catch (err) { setDeleteError(messageFrom(err)); }
  }
  async function remove() {
    if (!client || deleteName.trim() !== client.name.trim()) return;
    setBusy(true); setDeleteError(null);
    try { await api(`/clients/${id}`, { method: "DELETE" }); toast.success(t("clients.detail.clientDeleted", { name: client.name })); router.push("/clients"); }
    catch (err) { setDeleteError(messageFrom(err)); setBusy(false); }
  }

  if (!client) return <div className="page"><FormSkeleton sections={2} /></div>;
  // The portal lives under whatever host is serving this app, so the prefix
  // and the preview follow the browser origin. A verified custom domain
  // serves the portal at its root instead (see proxy.ts).
  const origin = typeof window === "undefined" ? "" : window.location.origin;
  const defaultPortalUrl = `${origin}/portal/${client.portal_slug}`;
  const portalUrl = domain?.verified && domain.domain ? `https://${domain.domain}` : defaultPortalUrl;
  return <div className="page">
    <Link href="/clients" className="back-link"><ArrowLeft size={17} /> {t("clients.detail.back")}</Link>
    <header className="entity-header"><div className="entity-avatar xl">{client.name.slice(0, 2).toUpperCase()}</div><div><div className="title-line"><h1>{client.name}</h1><StatusBadge active={client.is_active} /></div><p>{businessLabel(catalog, client, lang) || t("clients.detail.industryUndefined")} · {client.agents.length === 1 ? t("clients.detail.agentOne", { count: client.agents.length }) : t("clients.detail.agentMany", { count: client.agents.length })}</p></div><div className="header-actions"><Link href={`/agents/new?client=${client.id}`} className="button primary"><Bot size={17} /> {t("clients.detail.newAgent")}</Link></div></header>
    <nav className="tabs client-tabs"><button className={tab === "details" ? "active" : ""} onClick={() => setTab("details")}><Settings2 size={17} /> {t("clients.detail.tabDetails")}</button><button className={tab === "agents" ? "active" : ""} onClick={() => setTab("agents")}><Bot size={17} /> {t("clients.detail.tabAgents")} <span>{client.agents.length}</span></button><button className={tab === "channels" ? "active" : ""} onClick={() => setTab("channels")}><Radio size={17} /> {t("clients.detail.tabChannels")}</button><button className={tab === "inbox" ? "active" : ""} onClick={() => setTab("inbox")}><Inbox size={17} /> {t("clients.detail.tabInbox")}</button><button className={tab === "teams" ? "active" : ""} onClick={() => setTab("teams")}><Users size={17} /> {t("clients.detail.tabTeams")}</button><button className={tab === "templates" ? "active" : ""} onClick={() => setTab("templates")}><FileText size={17} /> {t("clients.detail.tabTemplates")}</button><button className={tab === "portal" ? "active" : ""} onClick={() => setTab("portal")}><Globe2 size={17} /> {t("clients.detail.tabPortal")}</button></nav>

    {tab === "details" && <form className="page-form" onSubmit={saveDetails}><section className="form-section"><div className="section-copy"><h2>{t("clients.detail.clientInfo")}</h2><p>{t("clients.detail.clientInfoCopy")}</p></div><div className="form-fields"><div className="logo-editor"><button type="button" className="logo-preview" onClick={() => logoRef.current?.click()}>{client.logo_url ? <img src={`${client.logo_url}&r=${logoVersion}`} alt={t("clients.detail.logoAlt")} /> : <ImagePlus size={24} />}</button><div><strong>{t("clients.detail.logoLabel")}</strong><small>{t("clients.detail.logoHint")}</small><div><button type="button" className="text-button" onClick={() => logoRef.current?.click()}>{t("clients.detail.logoChange")}</button>{client.logo_url && <button type="button" className="text-button danger-text" onClick={deleteLogo}><Trash2 size={14} /> {t("clients.detail.logoRemove")}</button>}</div></div><input ref={logoRef} hidden type="file" accept="image/png,image/jpeg,image/webp,image/svg+xml" onChange={(e) => uploadLogo(e.target.files?.[0])} /></div><IndustryPicker value={business} onChange={setBusiness} /><label><span className="label-row">{t("clients.detail.name")} <AiHint text={t("aiContext.businessName")} /></span><input name="name" required defaultValue={client.name} /></label><label>{t("clients.detail.timezoneLabel")}<Combobox value={timezone} onChange={setTimezone} options={TIMEZONES} placeholder={t("clients.detail.timezoneLabel")} /><span className="field-help">{t("clients.detail.timezoneHint")}</span></label><label className="switch-row"><span><strong>{t("clients.detail.activeClient")}</strong><small>{t("clients.detail.activeClientHint")}</small></span><input name="is_active" type="checkbox" defaultChecked={client.is_active} /></label></div></section><div className="form-footer split"><button type="button" className="button danger" onClick={openDelete}><Trash2 size={16} /> {t("clients.detail.deleteClient")}</button><button className="button primary" disabled={busy || !isBusinessComplete(business)}>{busy ? <LoaderCircle className="spin" size={17} /> : <Save size={17} />} {t("clients.detail.saveChanges")}</button></div></form>}

    <Modal open={deleteOpen} title={t("clients.detail.deleteTitle", { name: client.name })} onClose={() => setDeleteOpen(false)}>
      <div className="modal-form">
        <p className="modal-copy">{t("clients.detail.deleteCopy")}</p>
        {deletePreview ? <ul className="deletion-list">
          <li><strong>{deletePreview.agents}</strong> {t("clients.detail.deleteCountAgents")}</li>
          <li><strong>{deletePreview.channels}</strong> {t("clients.detail.deleteCountChannels")}</li>
          <li><strong>{deletePreview.conversations}</strong> {t("clients.detail.deleteCountConversations")}</li>
          <li><strong>{deletePreview.contacts}</strong> {t("clients.detail.deleteCountContacts")}</li>
          <li><strong>{deletePreview.portal_users}</strong> {t("clients.detail.deleteCountPortalUsers")}</li>
        </ul> : !deleteError && <p className="field-help"><LoaderCircle className="spin" size={14} /></p>}
        <label>{t("clients.detail.deleteTypeName", { name: client.name })}<input value={deleteName} onChange={(e) => setDeleteName(e.target.value)} autoComplete="off" placeholder={client.name} /></label>
        {deleteError && <Alert>{deleteError}</Alert>}
        <div className="modal-actions"><button type="button" className="button" onClick={() => setDeleteOpen(false)}>{t("common.cancel")}</button><button type="button" className="button danger" disabled={busy || !deletePreview || deleteName.trim() !== client.name.trim()} onClick={remove}>{busy ? <LoaderCircle className="spin" size={16} /> : <><Trash2 size={15} /> {t("clients.detail.deleteClient")}</>}</button></div>
      </div>
    </Modal>
    {tab === "agents" && (client.agents.length ? <div className="table-shell"><table className="data-table"><thead><tr><th>{t("clients.detail.colAgent")}</th><th>{t("clients.detail.colStatus")}</th><th /></tr></thead><tbody>{client.agents.map((agent) => <tr key={agent.id}><td><Link className="entity-cell" href={`/agents/${agent.id}`}><span className="agent-avatar"><Bot size={18} /></span><strong>{agent.name}</strong></Link></td><td><StatusBadge active={agent.is_active} /></td><td><Link className="row-arrow" href={`/agents/${agent.id}`}><ArrowRight size={17} /></Link></td></tr>)}</tbody></table></div> : <EmptyState icon={<Bot />} title={t("clients.detail.agentsEmptyTitle")} description={t("clients.detail.agentsEmptyDescription")} action={<Link href={`/agents/new?client=${client.id}`} className="button primary">{t("clients.detail.createAgent")}</Link>} />)}

    {tab === "channels" && <section className="compact-channel-grid"><article className={channelState("whatsapp_cloud") === "connected" ? "channel-live" : ""}><span><MessageCircle size={20} /></span><div><strong>{t("channels.whatsappCloud.title")} <ChannelStateBadge state={channelState("whatsapp_cloud")} /></strong><small>{channelDetail("whatsapp_cloud") || t("clients.detail.channelWhatsappAvailable", { name: client.name })}</small></div><Link className="button secondary" href={`/clients/${client.id}/channels/whatsapp-cloud`}>{t("clients.detail.configure")}</Link></article><article className={channelState("whatsapp") === "connected" ? "channel-live" : ""}><span><QrCode size={20} /></span><div><strong>{t("channels.whatsapp.title")} <ChannelStateBadge state={channelState("whatsapp")} /></strong><small>{channelDetail("whatsapp") || t("clients.detail.channelWhatsappQrAvailable")}</small></div><Link className="button secondary" href={`/clients/${client.id}/channels/whatsapp`}>{t("clients.detail.configure")}</Link></article><article className={channelState("webchat") === "connected" ? "channel-live" : ""}><span><Globe2 size={20} /></span><div><strong>{t("channels.webchat.title")} <ChannelStateBadge state={channelState("webchat")} /></strong><small>{t("clients.detail.channelWebchatAvailable")}</small></div><Link className="button secondary" href={`/clients/${client.id}/channels/webchat`}>{t("clients.detail.configure")}</Link></article>{(["instagram", "messenger"] as const).map((provider) => <article key={provider} className={channelState(provider) === "connected" ? "channel-live" : ""}><span><ChannelIcon channel={provider} size={20} /></span><div><strong>{t(`social.${provider}.title`)} <ChannelStateBadge state={channelState(provider)} /></strong><small>{channelDetail(provider) || t(`social.${provider}.description`)}</small></div><Link className="button secondary" href={`/clients/${client.id}/channels/${provider}`}>{t("social.configure")}</Link></article>)}</section>}

    {tab === "inbox" && <ClientInbox clientId={client.id} />}

    {/* Teams and WhatsApp templates are the client's own, managed here or from its portal; the views are the portal's, pointed at the agency routes. */}
    {tab === "teams" && <div className="embedded-portal-view"><TeamsView base={`/clients/${client.id}`} /></div>}
    {tab === "templates" && <div className="embedded-portal-view"><TemplatesView base={`/clients/${client.id}`} /></div>}
    {tab === "portal" && <><form className="page-form" onSubmit={savePortal}><section className="form-section"><div className="section-copy"><h2>{t("clients.detail.portalTitle")}</h2><p>{t("clients.detail.portalCopy")}</p></div><div className="form-fields"><label>{t("clients.detail.portalTitleLabel")}<input name="portal_title" defaultValue={client.portal_title} placeholder={t("clients.detail.portalTitlePlaceholder", { name: client.name })} /></label><label>{t("clients.detail.portalUrl")}<div className="slug-input"><span>{origin.replace(/^https?:\/\//, "")}/portal/</span><input name="portal_slug" defaultValue={client.portal_slug} /></div></label><div className="url-preview"><code>{portalUrl}</code><button type="button" onClick={() => navigator.clipboard.writeText(portalUrl)}><Copy size={15} /> {t("clients.detail.copy")}</button>{client.portal_enabled && <a href={portalUrl} target="_blank"><ExternalLink size={15} /> {t("clients.detail.open")}</a>}</div><label className="switch-row"><span><strong>{t("clients.detail.publishPortal")}</strong><small>{t("clients.detail.publishPortalHint")}</small></span><input name="portal_enabled" type="checkbox" defaultChecked={client.portal_enabled} /></label></div></section><div className="form-footer"><button className="button primary" disabled={busy}>{busy ? <LoaderCircle className="spin" size={17} /> : <Save size={17} />} {t("clients.detail.savePortal")}</button></div></form><PortalUsers clientId={client.id} /><PortalDomain clientId={client.id} domain={domain} onChange={setDomain} /></>}
  </div>;
}

function PortalUsers({ clientId }: { clientId: string }) {
  const t = useT();
  const toast = useToast();
  const [users, setUsers] = useState<PortalUser[] | null>(null);
  const [busy, setBusy] = useState(false);
  // "new" opens the create dialog; a user opens the edit dialog for them.
  const [editing, setEditing] = useState<PortalUser | "new" | null>(null);
  const [deleting, setDeleting] = useState<PortalUser | null>(null);
  const [suspending, setSuspending] = useState<PortalUser | null>(null);
  const [modalError, setModalError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setUsers(await api<PortalUser[]>(`/clients/${clientId}/portal-users`));
  }, [clientId]);
  useEffect(() => { load().catch(() => {}); }, [load]);

  function open(target: PortalUser | "new") { setModalError(null); setEditing(target); }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!editing) return;
    const data = new FormData(event.currentTarget);
    const password = String(data.get("password") || "");
    if (editing === "new" && password !== String(data.get("password_confirm") || "")) { setModalError(t("clients.detail.portalUserPasswordMismatch")); return; }
    const payload: Record<string, string> = { name: String(data.get("name") || "").trim(), email: String(data.get("email") || "").trim(), role: String(data.get("role") || "agent") };
    if (password) payload.password = password;
    setBusy(true); setModalError(null);
    try {
      if (editing === "new") {
        await api(`/clients/${clientId}/portal-users`, { method: "POST", body: JSON.stringify(payload) });
        toast.success(t("clients.detail.portalUserAdded"));
      } else {
        await api(`/clients/${clientId}/portal-users/${editing.id}`, { method: "PATCH", body: JSON.stringify(payload) });
        toast.success(t("clients.detail.portalUserSaved"));
      }
      setEditing(null);
      await load();
    } catch (err) { setModalError(messageFrom(err)); } finally { setBusy(false); }
  }
  async function setActive(u: PortalUser, active: boolean) {
    setBusy(true); setModalError(null);
    try {
      await api(`/clients/${clientId}/portal-users/${u.id}`, { method: "PATCH", body: JSON.stringify({ is_active: active }) });
      setSuspending(null);
      await load();
    } catch (err) { if (suspending) setModalError(messageFrom(err)); else toast.error(messageFrom(err)); } finally { setBusy(false); }
  }
  async function removeUser() {
    if (!deleting) return;
    setBusy(true); setModalError(null);
    try {
      await api(`/clients/${clientId}/portal-users/${deleting.id}`, { method: "DELETE" });
      toast.success(t("clients.detail.portalUserRemoved"));
      setDeleting(null);
      await load();
    } catch (err) { setModalError(messageFrom(err)); } finally { setBusy(false); }
  }

  const creating = editing === "new";
  const current = editing && editing !== "new" ? editing : null;
  // The first person at a business runs it; the ones added later work the inbox.
  const defaultRole: PortalRole = current ? current.role : (users?.length ? "agent" : "admin");
  const roleLabel = (role: PortalRole) => (role === "admin" ? t("clients.detail.portalUserRoleAdmin") : t("clients.detail.portalUserRoleAgent"));

  return <section className="form-section"><div className="section-copy"><h2>{t("clients.detail.portalUsersTitle")}</h2><p>{t("clients.detail.portalUsersCopy")}</p></div><div className="form-fields">
    {users === null ? <ListRowsSkeleton rows={2} /> : users.length ? <div className="table-shell"><table className="data-table"><tbody>
      {users.map((u) => <tr key={u.id}>
        <td><span className="entity-cell"><span className="agent-avatar"><UserRound size={17} /></span><span><span className="name-line"><strong>{u.name || u.email}</strong><span className={`mini-badge ${u.role === "admin" ? "human" : "ai"}`}>{roleLabel(u.role)}</span><StatusBadge active={u.is_active} /></span>{u.name && <small style={{ display: "block", color: "#89909d" }}>{u.email}</small>}</span></span></td>
        <td className="row-end"><span className="row-actions">
          <button type="button" className="button secondary small" disabled={busy} onClick={() => (u.is_active ? (setModalError(null), setSuspending(u)) : setActive(u, true))}>{u.is_active ? <><UserX size={14} /> {t("clients.detail.portalUserSuspend")}</> : <><UserCheck size={14} /> {t("clients.detail.portalUserActivate")}</>}</button>
          <span className="row-sep" />
          <button type="button" className="icon-button" onClick={() => open(u)} aria-label={t("clients.detail.portalUserEdit")} title={t("clients.detail.portalUserEdit")}><Pencil size={15} /></button>
          <button type="button" className="icon-button danger-icon" onClick={() => { setModalError(null); setDeleting(u); }} aria-label={t("clients.detail.portalUserRemove")} title={t("clients.detail.portalUserRemove")}><Trash2 size={15} /></button>
        </span></td>
      </tr>)}
    </tbody></table></div> : <p className="field-help">{t("clients.detail.portalUsersEmpty")}</p>}
    <button type="button" className="button secondary align-start" onClick={() => open("new")}><UserRound size={15} /> {t("clients.detail.portalUserAdd")}</button>

    <Modal open={editing !== null} title={creating ? t("clients.detail.portalUserAddTitle") : t("clients.detail.portalUserEditTitle", { name: current?.name || current?.email || "" })} description={creating ? t("clients.detail.portalUserAddCopy") : undefined} onClose={() => setEditing(null)}>
      <form key={creating ? "new" : current?.id} className="modal-form" onSubmit={save}>
        <div className="form-grid">
          <label>{t("clients.detail.portalUserName")}<input name="name" required minLength={2} maxLength={160} defaultValue={current?.name || ""} autoFocus /></label>
          <label>{t("clients.detail.portalUserEmail")}<input name="email" required type="email" defaultValue={current?.email || ""} placeholder={t("clients.detail.portalEmailPlaceholder")} /></label>
        </div>
        <label>{t("clients.detail.portalUserRole")}<select name="role" defaultValue={defaultRole}><option value="admin">{t("clients.detail.portalUserRoleAdmin")}</option><option value="agent">{t("clients.detail.portalUserRoleAgent")}</option></select><span className="field-help">{t("clients.detail.portalUserRoleHint")}</span></label>
        {creating ? <div className="form-grid">
          <label>{t("clients.detail.portalUserPassword")}<PasswordInput name="password" required minLength={8} autoComplete="new-password" placeholder={t("clients.detail.portalPasswordMin")} /></label>
          <label>{t("clients.detail.portalUserConfirmPassword")}<PasswordInput name="password_confirm" required minLength={8} autoComplete="new-password" placeholder={t("clients.detail.portalUserConfirmPlaceholder")} /></label>
        </div> : <label>{t("clients.detail.portalUserNewPassword")}<PasswordInput name="password" minLength={8} autoComplete="new-password" placeholder={t("clients.detail.portalUserPasswordKeep")} /><span className="field-help">{t("clients.detail.portalUserNewPasswordHint")}</span></label>}
        {modalError && <Alert>{modalError}</Alert>}
        <div className="modal-actions"><button type="button" className="button" onClick={() => setEditing(null)}>{t("common.cancel")}</button><button className="button primary" disabled={busy}>{busy ? <LoaderCircle className="spin" size={16} /> : creating ? t("clients.detail.portalUserAdd") : t("common.saveChanges")}</button></div>
      </form>
    </Modal>
    <Modal open={suspending !== null} title={t("clients.detail.portalUserSuspendTitle", { name: suspending?.name || suspending?.email || "" })} onClose={() => setSuspending(null)}>
      <div className="modal-form">
        <p className="modal-copy">{t("clients.detail.portalUserSuspendCopy")}</p>
        {modalError && <Alert>{modalError}</Alert>}
        <div className="modal-actions"><button type="button" className="button" onClick={() => setSuspending(null)}>{t("common.cancel")}</button><button type="button" className="button primary" disabled={busy} onClick={() => suspending && setActive(suspending, false)}>{busy ? <LoaderCircle className="spin" size={16} /> : <><UserX size={15} /> {t("clients.detail.portalUserSuspend")}</>}</button></div>
      </div>
    </Modal>
    <Modal open={deleting !== null} title={t("clients.detail.portalUserRemoveTitle", { name: deleting?.name || deleting?.email || "" })} onClose={() => setDeleting(null)}>
      <div className="modal-form">
        <p className="modal-copy">{t("clients.detail.portalUserRemoveCopy")}</p>
        {modalError && <Alert>{modalError}</Alert>}
        <div className="modal-actions"><button type="button" className="button" onClick={() => setDeleting(null)}>{t("common.cancel")}</button><button type="button" className="button danger" disabled={busy} onClick={removeUser}>{busy ? <LoaderCircle className="spin" size={16} /> : <><Trash2 size={15} /> {t("clients.detail.portalUserRemove")}</>}</button></div>
      </div>
    </Modal>
  </div></section>;
}

function PortalDomain({ clientId, domain, onChange }: { clientId: string; domain: ClientDomain | null; onChange: (domain: ClientDomain) => void }) {
  const t = useT();
  const toast = useToast();
  const setDomain = onChange;
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => { setInput(domain?.domain || ""); }, [domain?.domain]);

  async function save() {
    setBusy(true);
    try { const d = await api<ClientDomain>(`/clients/${clientId}/domain`, { method: "PUT", body: JSON.stringify({ domain: input.trim().toLowerCase() }) }); setDomain(d); toast.success(t("clients.detail.domainSaved")); }
    catch (err) { toast.error(messageFrom(err)); } finally { setBusy(false); }
  }
  async function verify() {
    setBusy(true);
    try { const d = await api<ClientDomain>(`/clients/${clientId}/domain/verify`, { method: "POST" }); setDomain(d); toast.success(t("clients.detail.domainVerified")); }
    catch (err) { toast.error(messageFrom(err)); } finally { setBusy(false); }
  }
  async function remove() {
    setBusy(true);
    try { const d = await api<ClientDomain>(`/clients/${clientId}/domain`, { method: "DELETE" }); setDomain(d); setInput(""); toast.success(t("clients.detail.domainRemoved")); }
    catch (err) { toast.error(messageFrom(err)); } finally { setBusy(false); }
  }

  return <section className="form-section domain-section"><div className="section-copy"><h2>{t("clients.detail.domainTitle")}</h2><p>{t("clients.detail.domainCopy")}</p></div><div className="form-fields">
    <label>{t("clients.detail.domainLabel")}<div className="domain-input"><Globe2 size={16} /><input value={input} onChange={(e) => setInput(e.target.value)} placeholder="chat.brand.com" /><button type="button" className="button secondary" onClick={save} disabled={busy || !input.trim()}><Save size={15} /> {t("clients.detail.domainSave")}</button></div></label>
    {domain?.domain && <>
      <div className={`domain-status ${domain.verified ? "ok" : "pending"}`}>{domain.verified ? <><ShieldCheck size={16} /> {t("clients.detail.domainStatusVerified")}</> : <><ShieldAlert size={16} /> {t("clients.detail.domainStatusPending")}</>}</div>
      {!domain.verified && <div className="dns-instructions">
        <p>{t("clients.detail.domainDnsIntro")}</p>
        <table className="dns-table"><thead><tr><th>{t("clients.detail.domainDnsType")}</th><th>{t("clients.detail.domainDnsHost")}</th><th>{t("clients.detail.domainDnsValue")}</th></tr></thead><tbody>
          <tr><td>CNAME</td><td><code>{domain.domain}</code></td><td><code>{t("clients.detail.domainCnameTarget")}</code></td></tr>
          <tr><td>TXT</td><td><code>{domain.txt_host}</code></td><td><code>{domain.txt_value}</code></td></tr>
        </tbody></table>
        <div className="domain-actions"><button type="button" className="button primary" onClick={verify} disabled={busy}>{busy ? <LoaderCircle className="spin" size={15} /> : <ShieldCheck size={15} />} {t("clients.detail.domainVerify")}</button></div>
      </div>}
      <div className="form-footer"><button type="button" className="button danger" onClick={remove} disabled={busy}><Trash2 size={15} /> {t("clients.detail.domainRemove")}</button></div>
    </>}
  </div></section>;
}

function ClientInbox({ clientId }: { clientId: string }) {
  const t = useT();
  const toast = useToast();
  const [items, setItems] = useState<Conversation[]>([]);
  const [selected, setSelected] = useState<Conversation | null>(null);
  const [busy, setBusy] = useState(false);
  const policy = useReplyPolicy(selected);
  const load = async () => { const rows = await api<Conversation[]>(`/conversations?client_id=${clientId}`); setItems(rows); if (rows[0] && !selected) setSelected(await api<Conversation>(`/conversations/${rows[0].id}`)); };
  const [loadedInbox, setLoadedInbox] = useState(false);
  useEffect(() => { load().catch(() => {}).finally(() => setLoadedInbox(true)); }, [clientId]);
  async function choose(item: Conversation) { setSelected(await api<Conversation>(`/conversations/${item.id}`)); }
  async function mode(next: "ai" | "human") { if (!selected) return; setSelected(await api<Conversation>(`/conversations/${selected.id}/mode`, { method: "PATCH", body: JSON.stringify({ mode: next }) })); await load(); }
  async function reply(event: FormEvent<HTMLFormElement>) { event.preventDefault(); if (!selected || !policy.canReply || busy) return; const form = event.currentTarget; const data = new FormData(form); setBusy(true); try { setSelected(await api<Conversation>(`/conversations/${selected.id}/reply`, { method: "POST", body: JSON.stringify({ content: data.get("content") }) })); form.reset(); await load(); } catch (err) { toast.error(messageFrom(err)); } finally { setBusy(false); } }
  if (!loadedInbox) return <ListRowsSkeleton rows={5} />;
  if (!items.length) return <EmptyState icon={<Inbox />} title={t("clients.detail.inboxEmptyTitle")} description={t("clients.detail.inboxEmptyDescription")} />;
  return <div className="inbox-layout"><aside className="inbox-list"><header><strong>{t("clients.detail.conversations")}</strong><span>{items.length}</span></header>{items.map((item) => <button key={item.id} className={selected?.id === item.id ? "active" : ""} onClick={() => choose(item)}><span className="entity-avatar tiny"><UserRound size={15} /></span><span><strong>{item.title}</strong><small>{channelLabel(item.channel, t)} · {item.mode === "human" ? t("clients.detail.modeHuman") : t("clients.detail.modeAi")}</small></span></button>)}</aside><section className="inbox-thread">{selected && <><header><div><strong>{selected.title}</strong><small>{channelLabel(selected.channel, t)}</small></div><button className={`mode-toggle ${selected.mode}`} onClick={() => mode(selected.mode === "ai" ? "human" : "ai")}>{selected.mode === "ai" ? t("clients.detail.takeControl") : t("clients.detail.returnToAi")}</button></header><div className="inbox-messages">{selected.messages?.map((message) => <div key={message.id} className={`inbox-message ${message.role}`}><small>{message.sender_name || (message.role === "assistant" ? t("clients.detail.senderAgent") : t("clients.detail.senderVisitor"))}</small><p>{message.content}</p></div>)}</div><SocialReplyNotice conversation={selected} blocked={policy.blocked} humanOnly={policy.humanOnly} /><form className="inbox-composer" onSubmit={reply}><input name="content" placeholder={selected.mode === "human" ? t("clients.detail.composerHuman") : t("clients.detail.composerLocked")} disabled={!policy.canReply || busy} required /><button disabled={!policy.canReply || busy}>{t("clients.detail.send")}</button></form></>}</section></div>;
}
