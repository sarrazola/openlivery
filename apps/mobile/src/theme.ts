/**
 * Colour.
 *
 * Two things are going on at once. The app is white label, so the agency's
 * colour arrives with the session and drives anything accented. Everything
 * else is a neutral palette that has to read well against any brand colour -
 * and has to follow the phone, because an app that stays white when the system
 * is dark is the first thing that makes it feel like a web page in a wrapper.
 *
 * Layout stays in StyleSheet.create; colours come from useColors() so they can
 * change with the system. Nothing here is configurable at runtime beyond that.
 */

import { useColorScheme } from "react-native";

export type Colors = {
  ink: string;
  muted: string;
  subtle: string;
  line: string;
  surface: string;
  /** Behind grouped content: slightly off from `surface` in both schemes. */
  canvas: string;
  /** Raised rows on top of `canvas`. */
  raised: string;
  danger: string;
  bubbleIn: string;
  /** A press highlight that works on either scheme. */
  pressed: string;
};

const light: Colors = {
  ink: "#17213b",
  muted: "#68718a",
  subtle: "#929ab0",
  line: "#e2e6ee",
  surface: "#ffffff",
  // The conversation sits on `canvas` and incoming bubbles are `bubbleIn`, so
  // those two carry the whole readability of a chat. They are pulled apart
  // deliberately: a received message has to be obvious at a glance, the way it
  // is in every messaging app.
  canvas: "#e7eaf0",
  raised: "#ffffff",
  danger: "#d95757",
  bubbleIn: "#ffffff",
  pressed: "rgba(0,0,0,0.05)",
};

const dark: Colors = {
  ink: "#f2f4f8",
  muted: "#9aa3b8",
  subtle: "#7b8399",
  line: "#2a2f3a",
  surface: "#161a21",
  canvas: "#0b0d11",
  raised: "#1c212a",
  danger: "#ff6b6b",
  bubbleIn: "#262d3a",
  pressed: "rgba(255,255,255,0.07)",
};

export function useColors(): Colors {
  return useColorScheme() === "dark" ? dark : light;
}

export function useIsDark(): boolean {
  return useColorScheme() === "dark";
}

/** Readable text colour for a filled brand-coloured surface. */
export function contrastOn(hex: string): string {
  const value = (hex || "").replace("#", "");
  if (value.length !== 6) return "#ffffff";
  const r = parseInt(value.slice(0, 2), 16);
  const g = parseInt(value.slice(2, 4), 16);
  const b = parseInt(value.slice(4, 6), 16);
  // Perceived luminance: green dominates what the eye reads as brightness.
  const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
  return luminance > 0.6 ? light.ink : "#ffffff";
}

/** A translucent wash of the brand colour, for selected rows and soft chips. */
export function tint(hex: string, alpha = 0.12): string {
  const value = (hex || "").replace("#", "");
  if (value.length !== 6) return `rgba(120, 120, 120, ${alpha})`;
  const r = parseInt(value.slice(0, 2), 16);
  const g = parseInt(value.slice(2, 4), 16);
  const b = parseInt(value.slice(4, 6), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

/**
 * Lift a brand colour until it is readable on a dark background.
 *
 * A deep navy brand is invisible on black. Rather than dropping the agency's
 * colour in dark mode, it is lightened just enough to carry accent text.
 */
export function readableBrand(hex: string, isDark: boolean): string {
  const value = (hex || "").replace("#", "");
  if (!isDark || value.length !== 6) return hex || light.ink;
  let [r, g, b] = [0, 2, 4].map((i) => parseInt(value.slice(i, i + 2), 16));
  let luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
  let guard = 0;
  while (luminance < 0.45 && guard++ < 12) {
    r = Math.min(255, Math.round(r + (255 - r) * 0.22));
    g = Math.min(255, Math.round(g + (255 - g) * 0.22));
    b = Math.min(255, Math.round(b + (255 - b) * 0.22));
    luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
  }
  return `#${[r, g, b].map((c) => c.toString(16).padStart(2, "0")).join("")}`;
}

export const DEFAULT_BRAND = "#2f3a4a";
