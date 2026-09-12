"use client";

import { LanguageSwitcher } from "@/components/language-switcher";
import { ThemeSwitcher } from "@/components/theme-switcher";
import { useT } from "@/lib/i18n";
import { TemplatesView } from "./templates";

/** The portal's settings: the person's own preferences, then what the business
 * configures. Templates need the WhatsApp API line and only an admin manages
 * them; the list is still shown so agents know what can be sent. */
export function SettingsView({ base, templatesSupported, canManageTemplates }: { base: string; templatesSupported: boolean; canManageTemplates: boolean }) {
  const t = useT();
  return <div className="portal-settings">
    <section>
      <div className="settings-copy"><h3>{t("portal.settings.preferencesTitle")}</h3><p>{t("portal.settings.preferencesCopy")}</p></div>
      <div className="sidebar-prefs portal-settings-prefs"><LanguageSwitcher /><ThemeSwitcher /></div>
    </section>
    <section>
      <div className="settings-copy"><h3>{t("portal.inbox.nav.templates")}</h3><p>{t("portal.settings.templatesCopy")}</p></div>
      <TemplatesView base={base} supported={templatesSupported} canManage={canManageTemplates} />
    </section>
  </div>;
}
