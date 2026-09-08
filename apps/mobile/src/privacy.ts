import { PRIVACY_POLICY_URLS, SUPPORT_URLS } from "./brand";

function localizedUrl(urls: { en?: string; es?: string }): string | undefined {
  let language = "en";
  try { language = require("expo-localization").getLocales()[0]?.languageCode || "en"; } catch { /* Script environment. */ }
  const value = (language === "es" ? urls.es : urls.en) || urls.en;
  if (!value) return undefined;
  try {
    const url = new URL(value);
    return url.protocol === "https:" && !url.username && !url.password ? url.toString() : undefined;
  } catch { return undefined; }
}

export const privacyUrl = () => localizedUrl(PRIVACY_POLICY_URLS);
export const supportUrl = () => localizedUrl(SUPPORT_URLS);
