"use client";

import { useEffect, useState, type ReactNode } from "react";
import { ChevronsUpDown, Languages, LogOut, Monitor, Moon, Sun, SunMoon } from "lucide-react";
import { useLanguage, type I18nKey } from "@/lib/i18n";
import { useTheme, type ThemePreference } from "@/lib/theme";

const THEMES: { value: ThemePreference; labelKey: I18nKey; icon: typeof Sun }[] = [
  { value: "light", labelKey: "shell.themeLight", icon: Sun },
  { value: "dark", labelKey: "shell.themeDark", icon: Moon },
  { value: "system", labelKey: "shell.themeSystem", icon: Monitor },
];

const LANGUAGES = [
  { value: "es", short: "ES", label: "Español" },
  { value: "en", short: "EN", label: "English" },
] as const;

function initials(name: string) {
  const words = name.trim().split(/\s+/).filter(Boolean);
  return words.slice(0, 2).map((word) => word[0]).join("").toUpperCase() || "?";
}

type MenuProps = {
  name: string;
  detail?: string | null;
  onLogout: () => void;
  // Rows a surface adds: `top` above the language, `children` below the theme.
  top?: ReactNode;
  children?: ReactNode;
};

/** What the menu holds: interface language and appearance (both kept on this
 * browser, never on the account), whatever the surface adds, and signing out. */
export function UserMenuItems({ onLogout, top, children, onClose }: Omit<MenuProps, "name" | "detail"> & { onClose?: () => void }) {
  const { lang, setLang, t } = useLanguage();
  const { preference, setTheme } = useTheme();
  return <>
    {top}
    <div className="user-menu-row">
      <span><Languages size={17} /> {t("shell.language")}</span>
      <div className="user-menu-options" role="group" aria-label={t("shell.language")}>
        {LANGUAGES.map((option) => (
          <button key={option.value} type="button" className={lang === option.value ? "active" : ""} aria-pressed={lang === option.value} aria-label={option.label} title={option.label} onClick={() => setLang(option.value)}>{option.short}</button>
        ))}
      </div>
    </div>
    <div className="user-menu-row">
      <span><SunMoon size={17} /> {t("shell.theme")}</span>
      <div className="user-menu-options" role="group" aria-label={t("shell.theme")}>
        {THEMES.map(({ value, labelKey, icon: Icon }) => (
          <button key={value} type="button" className={preference === value ? "active" : ""} aria-pressed={preference === value} aria-label={t(labelKey)} title={t(labelKey)} onClick={() => setTheme(value)}><Icon size={15} /></button>
        ))}
      </div>
    </div>
    {children}
    <div className="user-menu-sep" />
    <button type="button" role="menuitem" className="user-menu-item" onClick={() => { onClose?.(); onLogout(); }}><LogOut size={17} /> {t("shell.logout")}</button>
  </>;
}

// The person at the foot of the sidebar, opening their own menu above it
// (beside it when the sidebar is folded). `status` puts a dot on the avatar.
export function UserMenu({ name, detail, status, onLogout, top, children }: MenuProps & { status?: "online" | "away" }) {
  const { t } = useLanguage();
  const [open, setOpen] = useState(false);
  useEffect(() => {
    if (!open) return;
    const close = (event: KeyboardEvent) => { if (event.key === "Escape") setOpen(false); };
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [open]);

  return <div className="sidebar-foot">
    <button type="button" className="user-menu-trigger" aria-haspopup="menu" aria-expanded={open} title={t("shell.accountMenu")} onClick={() => setOpen((v) => !v)}>
      <div className="user-avatar">{initials(name)}{status && <i className={`user-status ${status}`} aria-hidden="true" />}</div>
      <div className="user-meta"><strong>{name}</strong>{detail && <span>{detail}</span>}</div>
      <ChevronsUpDown size={15} />
    </button>
    {open && <>
      <div className="menu-backdrop" onClick={() => setOpen(false)} />
      <div className="user-menu" role="menu" aria-label={t("shell.accountMenu")}>
        <div className="user-menu-head"><strong>{name}</strong>{detail && <span>{detail}</span>}</div>
        <UserMenuItems onLogout={onLogout} top={top} onClose={() => setOpen(false)}>{children}</UserMenuItems>
      </div>
    </>}
  </div>;
}
