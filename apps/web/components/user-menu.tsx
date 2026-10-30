"use client";

import { useEffect, useState } from "react";
import { ChevronsUpDown, Languages, LogOut, Monitor, Moon, Sun, SunMoon } from "lucide-react";
import { useLanguage, type I18nKey } from "@/lib/i18n";
import { useTheme, type ThemePreference } from "@/lib/theme";
import type { User } from "@/types";

const THEMES: { value: ThemePreference; labelKey: I18nKey; icon: typeof Sun }[] = [
  { value: "system", labelKey: "shell.themeSystem", icon: Monitor },
  { value: "light", labelKey: "shell.themeLight", icon: Sun },
  { value: "dark", labelKey: "shell.themeDark", icon: Moon },
];

// The person at the foot of the sidebar, opening their own menu: interface
// language and appearance (both kept on this browser, never on the agency)
// and signing out.
export function UserMenu({ user, onLogout }: { user: User; onLogout: () => void }) {
  const { lang, setLang, t } = useLanguage();
  const { preference, setTheme } = useTheme();
  const [open, setOpen] = useState(false);
  useEffect(() => {
    if (!open) return;
    const close = (event: KeyboardEvent) => { if (event.key === "Escape") setOpen(false); };
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [open]);

  return <div className="sidebar-foot">
    <button type="button" className="user-menu-trigger" aria-haspopup="menu" aria-expanded={open} title={t("shell.accountMenu")} onClick={() => setOpen((v) => !v)}>
      <div className="user-avatar">{user.name.slice(0, 1).toUpperCase()}</div>
      <div className="user-meta"><strong>{user.name}</strong><span>{user.email}</span></div>
      <ChevronsUpDown size={15} />
    </button>
    {open && <>
      <div className="menu-backdrop" onClick={() => setOpen(false)} />
      <div className="user-menu" role="menu" aria-label={t("shell.accountMenu")}>
        <div className="user-menu-head"><strong>{user.name}</strong><span>{user.email}</span></div>
        <div className="user-menu-group">
          <span><Languages size={14} /> {t("settings.preferences.language")}</span>
          <div className="user-menu-options" role="group" aria-label={t("settings.preferences.language")}>
            <button type="button" className={lang === "en" ? "active" : ""} aria-pressed={lang === "en"} onClick={() => setLang("en")}>English</button>
            <button type="button" className={lang === "es" ? "active" : ""} aria-pressed={lang === "es"} onClick={() => setLang("es")}>Español</button>
          </div>
        </div>
        <div className="user-menu-group">
          <span><SunMoon size={14} /> {t("settings.preferences.appearance")}</span>
          <div className="user-menu-options" role="group" aria-label={t("settings.preferences.appearance")}>
            {THEMES.map(({ value, labelKey, icon: Icon }) => (
              <button key={value} type="button" className={preference === value ? "active" : ""} aria-pressed={preference === value} onClick={() => setTheme(value)}><Icon size={13} /> {t(labelKey)}</button>
            ))}
          </div>
        </div>
        <button type="button" role="menuitem" className="user-menu-item" onClick={() => { setOpen(false); onLogout(); }}><LogOut size={15} /> {t("shell.logout")}</button>
      </div>
    </>}
  </div>;
}
