"use client";

import { Monitor, Moon, Sun } from "lucide-react";
import { useT, type I18nKey } from "@/lib/i18n";
import { useTheme, type ThemePreference } from "@/lib/theme";

const ORDER: ThemePreference[] = ["system", "light", "dark"];
const OPTIONS: Record<ThemePreference, { labelKey: I18nKey; icon: typeof Sun }> = {
  system: { labelKey: "shell.themeSystem", icon: Monitor },
  light: { labelKey: "shell.themeLight", icon: Sun },
  dark: { labelKey: "shell.themeDark", icon: Moon },
};

// Appearance preference row in the sidebar footer: one button that shows the
// current mode and cycles system, light, dark on each press.
export function ThemeSwitcher() {
  const t = useT();
  const { preference, setTheme } = useTheme();
  const { labelKey, icon: Icon } = OPTIONS[preference];
  const next = ORDER[(ORDER.indexOf(preference) + 1) % ORDER.length];
  return (
    <div className="pref-row">
      <span><Sun size={14} />{t("shell.theme")}</span>
      <button type="button" className="pref-cycle" onClick={() => setTheme(next)} title={t(OPTIONS[next].labelKey)} aria-label={`${t("shell.theme")}: ${t(labelKey)}`}>
        <Icon size={14} /> {t(labelKey)}
      </button>
    </div>
  );
}
