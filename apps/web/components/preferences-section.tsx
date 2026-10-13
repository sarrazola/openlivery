"use client";

import { useEffect, useState } from "react";
import { BellRing, Languages, Monitor, Moon, Smartphone, Sun, SunMoon } from "lucide-react";
import { useLanguage, type I18nKey } from "@/lib/i18n";
import { useTheme, type ThemePreference } from "@/lib/theme";
import { disablePush, enablePush, pushConfig, pushState, type PushState, type WebPushConfig } from "@/lib/web-push";
import { api } from "@/lib/api";
import type { PortalPublic } from "@/types";
import { AppBadges } from "@/components/app-badges";

const THEMES: { value: ThemePreference; labelKey: I18nKey; icon: typeof Sun }[] = [
  { value: "system", labelKey: "shell.themeSystem", icon: Monitor },
  { value: "light", labelKey: "shell.themeLight", icon: Sun },
  { value: "dark", labelKey: "shell.themeDark", icon: Moon },
];

// Settings section for the per-person, per-browser preferences: interface
// language and appearance. Both are stored locally, never on the agency.
// In a portal it also offers browser notifications for the person signed in,
// when the server can send them (see lib/web-push.ts).
export function PreferencesSection({ pushSlug }: { pushSlug?: string } = {}) {
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
        {pushSlug && <PushRow slug={pushSlug} />}
        {pushSlug && <MobileAppRow slug={pushSlug} />}
      </div>
    </section>
  );
}

// Where to get the mobile app, when the deployment publishes one.
function MobileAppRow({ slug }: { slug: string }) {
  const { t } = useLanguage();
  const [links, setLinks] = useState<{ ios?: string | null; android?: string | null } | null>(null);
  useEffect(() => {
    let alive = true;
    api<PortalPublic>(`/portal/${slug}`).then((info) => { if (alive) setLinks({ ios: info.ios_app_url, android: info.android_app_url }); }).catch(() => {});
    return () => { alive = false; };
  }, [slug]);
  if (!links || (!links.ios && !links.android)) return null;
  return (
    <div className="switch-row compact mobile-app-row">
      <span><strong><Smartphone size={14} /> {t("settings.preferences.mobileApp")}</strong><small>{t("settings.preferences.mobileAppHint")}</small></span>
      <AppBadges ios={links.ios} android={links.android} />
    </div>
  );
}

// The notifications switch. Hidden while the server cannot send to browsers,
// disabled when this browser cannot receive, and otherwise the person's own
// on/off for this browser.
function PushRow({ slug }: { slug: string }) {
  const { t } = useLanguage();
  const [config, setConfig] = useState<WebPushConfig | null>(null);
  const [state, setState] = useState<PushState>("off");
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let alive = true;
    pushConfig(slug).then(async (loaded) => {
      const current = await pushState(slug, loaded);
      if (!alive) return;
      setConfig(loaded); setState(current);
    });
    return () => { alive = false; };
  }, [slug]);
  if (!config || state === "unavailable") return null;
  const blocked = state === "unsupported" || state === "denied";
  async function toggle(on: boolean) {
    setBusy(true); setFailed(false);
    try {
      setState(on ? await enablePush(slug, config ?? undefined) : await disablePush(slug));
    } catch {
      setFailed(true);
    } finally {
      setBusy(false);
    }
  }
  const hint = state === "unsupported" ? t("settings.preferences.notificationsUnsupported")
    : state === "denied" ? t("settings.preferences.notificationsDenied")
    : failed ? t("settings.preferences.notificationsFailed")
    : state === "on" ? t("settings.preferences.notificationsOn")
    : t("settings.preferences.notificationsHint");
  return (
    <label className="switch-row compact">
      <span><strong><BellRing size={14} /> {t("settings.preferences.notifications")}</strong><small>{hint}</small></span>
      <input type="checkbox" checked={state === "on"} disabled={blocked || busy} onChange={(event) => toggle(event.target.checked)} />
    </label>
  );
}
