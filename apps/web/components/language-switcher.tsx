"use client";

import { Languages } from "lucide-react";
import { useLanguage } from "@/lib/i18n";

// Language preference row in the sidebar footers: label on the left, EN/ES
// segmented control on the right. Shares its layout with the theme switcher.
export function LanguageSwitcher() {
  const { lang, setLang, t } = useLanguage();
  return (
    <div className="pref-row">
      <span><Languages size={14} />{t("shell.language")}</span>
      <div role="group" aria-label={t("shell.language")}>
        <button type="button" className={lang === "en" ? "active" : ""} onClick={() => setLang("en")} aria-pressed={lang === "en"}>EN</button>
        <button type="button" className={lang === "es" ? "active" : ""} onClick={() => setLang("es")} aria-pressed={lang === "es"}>ES</button>
      </div>
    </div>
  );
}
