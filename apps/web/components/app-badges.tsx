"use client";

import { useLanguage } from "@/lib/i18n";

// The stores' own "Download on the App Store" and "Get it on Google Play"
// badges, served by Apple and Google themselves in the interface language, so
// no store artwork lives in this repository. Shown only for the stores the
// deployment configured (PORTAL_IOS_APP_URL, PORTAL_ANDROID_APP_URL).
export function AppBadges({ ios, android, className }: { ios?: string | null; android?: string | null; className?: string }) {
  const { lang } = useLanguage();
  if (!ios && !android) return null;
  const apple = `https://tools.applemediaservices.com/api/badges/download-on-the-app-store/black/${lang === "es" ? "es-mx" : "en-us"}?size=250x83`;
  const google = `https://play.google.com/intl/${lang === "es" ? "es-419" : "en_us"}/badges/static/images/badges/${lang === "es" ? "es-419" : "en"}_badge_web_generic.png`;
  return (
    <div className={`app-badges${className ? ` ${className}` : ""}`}>
      {ios && <a href={ios} target="_blank" rel="noopener noreferrer"><img className="badge-apple" src={apple} alt="App Store" /></a>}
      {android && <a href={android} target="_blank" rel="noopener noreferrer"><img className="badge-google" src={google} alt="Google Play" /></a>}
    </div>
  );
}
