"use client";

import { useState } from "react";
import { FileText, MessageSquareText, SlidersHorizontal, Tag, Users } from "lucide-react";
import { PreferencesSection } from "@/components/preferences-section";
import { useT } from "@/lib/i18n";
import { CannedRepliesView } from "./canned";
import { TagsView } from "./tags";
import { TeamsView } from "./teams";
import { TemplatesView } from "./templates";

type Tab = "preferences" | "teams" | "tags" | "canned" | "templates";

/** The portal's settings, in tabs: the person's own preferences first, then
 * what the business configures. Everyone can look; what each tab lets you
 * change follows the person's permissions. */
export function SettingsView({ slug, templatesSupported, can }: { slug: string; templatesSupported: boolean; can: (key: string) => boolean }) {
  const t = useT();
  const [tab, setTab] = useState<Tab>("preferences");
  const base = `/portal/${slug}`;
  return <div className="portal-settings">
    <nav className="tabs">
      <button className={tab === "preferences" ? "active" : ""} onClick={() => setTab("preferences")}><SlidersHorizontal size={16} /> {t("settings.preferences.heading")}</button>
      <button className={tab === "teams" ? "active" : ""} onClick={() => setTab("teams")}><Users size={16} /> {t("portal.inbox.nav.teams")}</button>
      <button className={tab === "tags" ? "active" : ""} onClick={() => setTab("tags")}><Tag size={16} /> {t("portal.contacts.tags.manageTitle")}</button>
      <button className={tab === "canned" ? "active" : ""} onClick={() => setTab("canned")}><MessageSquareText size={16} /> {t("portal.canned.manageTitle")}</button>
      <button className={tab === "templates" ? "active" : ""} onClick={() => setTab("templates")}><FileText size={16} /> {t("portal.inbox.nav.templates")}</button>
    </nav>
    {tab === "preferences" && <PreferencesSection />}
    {tab === "teams" && <TeamsView base={base} canManage={can("teams.manage")} />}
    {tab === "tags" && <TagsView base={`${base}/tags`} canManage={can("tags.manage")} />}
    {tab === "canned" && <CannedRepliesView slug={slug} canManage={can("canned.manage")} />}
    {tab === "templates" && <section className="form-section"><div className="section-copy"><h2>{t("portal.inbox.nav.templates")}</h2><p>{t("portal.settings.templatesCopy")}</p></div><div className="form-fields"><TemplatesView base={base} supported={templatesSupported} canManage={can("templates.manage")} /></div></section>}
  </div>;
}
