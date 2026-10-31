"use client";

import { useState } from "react";
import { FileText, MessageSquareText, Tag, Users } from "lucide-react";
import { SectionTabs, type SectionTab } from "@/components/section-tabs";
import { useT } from "@/lib/i18n";
import { CannedRepliesView } from "./canned";
import { TagsView } from "./tags";
import { TeamsView } from "./teams";
import { TemplatesView } from "./templates";

type Tab = "teams" | "tags" | "canned" | "templates";
const MANAGES: Record<Tab, string> = { teams: "teams.manage", tags: "tags.manage", canned: "canned.manage", templates: "templates.manage" };

/** Whether the person can manage anything here. Someone who cannot has no
 * Settings on a desktop: their own preferences live in the account menu. */
export function hasSettingsTabs(can: (key: string) => boolean): boolean {
  return Object.values(MANAGES).some(can);
}

/** What the business configures, in tabs. A tab shows only to someone whose
 * role can manage it; the person's own preferences are in the account menu. */
export function SettingsView({ slug, templatesSupported, can, tab: initialTab, onTab }: { slug: string; templatesSupported: boolean; can: (key: string) => boolean; tab?: string; onTab?: (tab: Tab) => void }) {
  const t = useT();
  const allowed = (Object.keys(MANAGES) as Tab[]).filter((key) => can(MANAGES[key]));
  const [tab, setTabState] = useState<Tab | undefined>(allowed.includes(initialTab as Tab) ? initialTab as Tab : allowed[0]);
  const setTab = (next: Tab) => { setTabState(next); onTab?.(next); };
  const base = `/portal/${slug}`;
  // SectionTabs keeps the strip on a desktop and pages through it on a phone.
  if (!tab) return null;
  const tabs: SectionTab<Tab>[] = [
    ...(can("teams.manage") ? [{ id: "teams" as const, label: t("portal.inbox.nav.teams"), icon: Users }] : []),
    ...(can("tags.manage") ? [{ id: "tags" as const, label: t("portal.contacts.tags.manageTitle"), icon: Tag }] : []),
    ...(can("canned.manage") ? [{ id: "canned" as const, label: t("portal.canned.manageTitle"), icon: MessageSquareText }] : []),
    ...(can("templates.manage") ? [{ id: "templates" as const, label: t("portal.inbox.nav.templates"), icon: FileText }] : []),
  ];
  return <div className="portal-settings">
    <SectionTabs<Tab> tabs={tabs} value={tab} onChange={setTab} />
    {tab === "teams" && can("teams.manage") && <TeamsView base={base} canManage />}
    {tab === "tags" && can("tags.manage") && <TagsView base={`${base}/tags`} canManage />}
    {tab === "canned" && can("canned.manage") && <CannedRepliesView slug={slug} canManage />}
    {tab === "templates" && can("templates.manage") && <section className="form-section"><div className="section-copy"><h2>{t("portal.inbox.nav.templates")}</h2><p>{t("portal.settings.templatesCopy")}</p></div><div className="form-fields"><TemplatesView base={base} supported={templatesSupported} canManage /></div></section>}
  </div>;
}
