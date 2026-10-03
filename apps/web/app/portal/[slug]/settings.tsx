"use client";

import { useState } from "react";
import { FileText, MessageSquareText, SlidersHorizontal, Tag, Users } from "lucide-react";
import { PreferencesSection } from "@/components/preferences-section";
import { SectionTabs, type SectionTab } from "@/components/section-tabs";
import { useT } from "@/lib/i18n";
import { CannedRepliesView } from "./canned";
import { TagsView } from "./tags";
import { TeamsView } from "./teams";
import { TemplatesView } from "./templates";

type Tab = "preferences" | "teams" | "tags" | "canned" | "templates";
const TABS: Tab[] = ["preferences", "teams", "tags", "canned", "templates"];

/** The portal's settings, in tabs: the person's own preferences first, then
 * what the business configures. A management tab shows only to someone whose
 * role can manage it; an agent sees Preferences and nothing else. */
export function SettingsView({ slug, templatesSupported, can, tab: initialTab, onTab }: { slug: string; templatesSupported: boolean; can: (key: string) => boolean; tab?: string; onTab?: (tab: Tab) => void }) {
  const t = useT();
  const [tab, setTabState] = useState<Tab>(initialTab && (TABS as string[]).includes(initialTab) ? initialTab as Tab : "preferences");
  const setTab = (next: Tab) => { setTabState(next); onTab?.(next); };
  const base = `/portal/${slug}`;
  // The same tabs as before; SectionTabs keeps the strip on a desktop and
  // pages through them on a phone. A tab the role cannot manage is left out.
  const tabs: SectionTab<Tab>[] = [
    { id: "preferences", label: t("settings.preferences.heading"), icon: SlidersHorizontal },
    ...(can("teams.manage") ? [{ id: "teams" as const, label: t("portal.inbox.nav.teams"), icon: Users }] : []),
    ...(can("tags.manage") ? [{ id: "tags" as const, label: t("portal.contacts.tags.manageTitle"), icon: Tag }] : []),
    ...(can("canned.manage") ? [{ id: "canned" as const, label: t("portal.canned.manageTitle"), icon: MessageSquareText }] : []),
    ...(can("templates.manage") ? [{ id: "templates" as const, label: t("portal.inbox.nav.templates"), icon: FileText }] : []),
  ];
  return <div className="portal-settings">
    <SectionTabs<Tab> tabs={tabs} value={tab} onChange={setTab} />
    {tab === "preferences" && <PreferencesSection />}
    {tab === "teams" && can("teams.manage") && <TeamsView base={base} canManage />}
    {tab === "tags" && can("tags.manage") && <TagsView base={`${base}/tags`} canManage />}
    {tab === "canned" && can("canned.manage") && <CannedRepliesView slug={slug} canManage />}
    {tab === "templates" && can("templates.manage") && <section className="form-section"><div className="section-copy"><h2>{t("portal.inbox.nav.templates")}</h2><p>{t("portal.settings.templatesCopy")}</p></div><div className="form-fields"><TemplatesView base={base} supported={templatesSupported} canManage /></div></section>}
  </div>;
}
