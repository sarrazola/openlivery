"use client";

import { Monitor, Moon, Sun, SunMoon } from "lucide-react";
import { useT, type I18nKey } from "@/lib/i18n";
import { useTheme, type ThemePreference } from "@/lib/theme";

const OPTIONS: { value: ThemePreference; labelKey: I18nKey; icon: typeof Sun }[] = [
  { value: "system", labelKey: "shell.themeSystem", icon: Monitor },
  { value: "light", labelKey: "shell.themeLight", icon: Sun },
  { value: "dark", labelKey: "shell.themeDark", icon: Moon },
];

// Compact system / light / dark toggle used in the sidebar footers, next to
// the language switcher.
export function ThemeSwitcher() {
  const t = useT();
  const { preference, setTheme } = useTheme();
  return (
    <div className="theme-switcher" role="group" aria-label={t("shell.theme")}>
      <SunMoon size={14} />
      {OPTIONS.map(({ value, labelKey, icon: Icon }) => (
        <button
          key={value}
          type="button"
          className={preference === value ? "active" : ""}
          onClick={() => setTheme(value)}
          aria-pressed={preference === value}
          aria-label={t(labelKey)}
          title={t(labelKey)}
        >
          <Icon size={14} />
        </button>
      ))}
    </div>
  );
}
