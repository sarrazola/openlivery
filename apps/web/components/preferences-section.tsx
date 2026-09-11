"use client";

import { Languages, Monitor, Moon, Sun, SunMoon } from "lucide-react";
import { useLanguage, type I18nKey } from "@/lib/i18n";
import { useTheme, type ThemePreference } from "@/lib/theme";

const THEMES: { value: ThemePreference; labelKey: I18nKey; icon: typeof Sun }[] = [
  { value: "system", labelKey: "shell.themeSystem", icon: Monitor },
  { value: "light", labelKey: "shell.themeLight", icon: Sun },
  { value: "dark", labelKey: "shell.themeDark", icon: Moon },
];

// Settings section for the per-person, per-browser preferences: interface
// language and appearance. Both are stored locally, never on the agency.
export function PreferencesSection() {
  const { lang, setLang, t } = useLanguage();
  const { preference, setTheme } = useTheme();
  return (
    <section className="form-section">
      <div className="section-copy"><h2>{t("settings.preferences.heading")}</h2><p>{t("settings.preferences.copy")}</p></div>
      <div className="form-fields pref-list">
        <div className="pref-row">
          <span><Languages size={16} /><span><strong>{t("settings.preferences.language")}</strong><small>{t("settings.preferences.languageHint")}</small></span></span>
          <div role="group" aria-label={t("settings.preferences.language")}>
            <button type="button" className={lang === "en" ? "active" : ""} onClick={() => setLang("en")} aria-pressed={lang === "en"}>English</button>
            <button type="button" className={lang === "es" ? "active" : ""} onClick={() => setLang("es")} aria-pressed={lang === "es"}>Español</button>
          </div>
        </div>
        <div className="pref-row">
          <span><SunMoon size={16} /><span><strong>{t("settings.preferences.appearance")}</strong><small>{t("settings.preferences.appearanceHint")}</small></span></span>
          <div role="group" aria-label={t("settings.preferences.appearance")}>
            {THEMES.map(({ value, labelKey, icon: Icon }) => (
              <button key={value} type="button" className={preference === value ? "active" : ""} onClick={() => setTheme(value)} aria-pressed={preference === value}>
                <Icon size={14} /> {t(labelKey)}
              </button>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
