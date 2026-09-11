"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState, ReactNode } from "react";
import { usePathname } from "next/navigation";

export type ThemePreference = "system" | "light" | "dark";
export type ResolvedTheme = "light" | "dark";

export const THEME_STORAGE_KEY = "openlivery.theme";
const PREFERENCES: ThemePreference[] = ["system", "light", "dark"];
const MEDIA_QUERY = "(prefers-color-scheme: dark)";

// The widget is embedded in a customer's page: it keeps its own look and never
// follows a preference stored for the agency app or the portal. Everything else
// under this origin shares one preference.
export function themeApplies(pathname: string): boolean {
  return !pathname.startsWith("/widget/");
}

function isPreference(value: unknown): value is ThemePreference {
  return typeof value === "string" && (PREFERENCES as string[]).includes(value);
}

// Mirrors the inline script in lib/theme-script.ts, which runs before first
// paint; keep the two in step.
export function readStoredTheme(): ThemePreference {
  if (typeof window === "undefined") return "system";
  try {
    const stored = window.localStorage.getItem(THEME_STORAGE_KEY);
    if (isPreference(stored)) return stored;
  } catch {
    // Storage can be unavailable (private mode, blocked site data).
  }
  const match = document.cookie.match(/(?:^|;\s*)openlivery\.theme=(system|light|dark)/);
  return match ? (match[1] as ThemePreference) : "system";
}

export function resolveTheme(preference: ThemePreference): ResolvedTheme {
  if (preference !== "system") return preference;
  if (typeof window === "undefined") return "light";
  return window.matchMedia(MEDIA_QUERY).matches ? "dark" : "light";
}

// The data-theme attribute is the only switch the stylesheet reads: "system" is
// resolved here, never in CSS, so a route that opts out simply carries no
// attribute. The theme-color meta keeps mobile browser chrome on the canvas.
export function applyTheme(resolved: ResolvedTheme) {
  const root = document.documentElement;
  root.dataset.theme = resolved;
  let meta = document.querySelector<HTMLMetaElement>('meta[name="theme-color"]');
  if (!meta) {
    meta = document.createElement("meta");
    meta.name = "theme-color";
    document.head.appendChild(meta);
  }
  const canvas = getComputedStyle(root).getPropertyValue("--canvas").trim();
  meta.content = canvas || (resolved === "dark" ? "#0d1220" : "#f7f9fa");
}

// Cross-fade the swap: the attribute enables a short transition on every
// color, and is dropped once the fade has run so components keep their own.
function withTransition(change: () => void) {
  const root = document.documentElement;
  root.setAttribute("data-theme-transition", "");
  // Force a style flush so the transition rule is in place before the colors change.
  void root.offsetWidth;
  change();
  window.setTimeout(() => root.removeAttribute("data-theme-transition"), 300);
}

type ThemeContextValue = {
  preference: ThemePreference;
  resolved: ResolvedTheme;
  setTheme: (preference: ThemePreference) => void;
};

const ThemeContext = createContext<ThemeContextValue | null>(null);

export function ThemeProvider({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const applies = themeApplies(pathname);
  // SSR renders no attribute; the inline script sets it before paint and this
  // effect picks the same value up on mount, so nothing changes at hydration.
  const [preference, setPreference] = useState<ThemePreference>("system");
  const [resolved, setResolved] = useState<ResolvedTheme>("light");

  useEffect(() => {
    if (!applies) {
      delete document.documentElement.dataset.theme;
      return;
    }
    const stored = readStoredTheme();
    const current = resolveTheme(stored);
    setPreference(stored);
    setResolved(current);
    applyTheme(current);
  }, [applies]);

  // Follow the operating system live while nothing is pinned.
  useEffect(() => {
    if (!applies || preference !== "system") return;
    const media = window.matchMedia(MEDIA_QUERY);
    const onChange = () => {
      const next = resolveTheme("system");
      setResolved(next);
      withTransition(() => applyTheme(next));
    };
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, [applies, preference]);

  const setTheme = useCallback((next: ThemePreference) => {
    setPreference(next);
    try {
      window.localStorage.setItem(THEME_STORAGE_KEY, next);
    } catch {
      // Fall through to the cookie.
    }
    document.cookie = `openlivery.theme=${next}; path=/; max-age=31536000; samesite=lax`;
    const current = resolveTheme(next);
    setResolved(current);
    withTransition(() => applyTheme(current));
  }, []);

  const value = useMemo(() => ({ preference, resolved, setTheme }), [preference, resolved, setTheme]);
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme must be used within ThemeProvider");
  return ctx;
}
