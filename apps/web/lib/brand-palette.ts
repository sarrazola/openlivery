import type { CSSProperties } from "react";

// An agency picks any color for its clients' portal, which uses it lightly:
// the sign-in button and a few small labels. Used raw, a light color leaves
// white text unreadable on the button and a dark one disappears as text in the
// dark theme, so the portal takes three things from it: the color for the
// button, the text that reads on it, and a version of the color that reads as
// text on the page in each theme.

type Rgb = [number, number, number];

const WHITE: Rgb = [255, 255, 255];
const BLACK: Rgb = [0, 0, 0];
const INK = "#102a43"; // --ink, light theme
const DARK_SURFACE: Rgb = [20, 26, 42]; // --surface, dark theme

function parse(color: string): Rgb | null {
  const match = /^#([0-9a-f]{6})$/i.exec(color.trim());
  if (!match) return null;
  const n = parseInt(match[1], 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

function luminance(rgb: Rgb): number {
  const [r, g, b] = rgb.map((value) => {
    const c = value / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrast(a: Rgb, b: Rgb): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

function toHex(rgb: Rgb): string {
  return `#${rgb.map((value) => Math.round(value).toString(16).padStart(2, "0")).join("")}`;
}

// Moves the color toward `target` in small steps until it reads on `page` as
// body text does (4.5:1). A color that already reads comes back unchanged.
function readableOn(color: Rgb, page: Rgb, target: Rgb): string {
  for (let step = 0; step <= 20; step++) {
    const t = step / 20;
    const mixed = color.map((value, i) => value + (target[i] - value) * t) as Rgb;
    if (contrast(mixed, page) >= 4.5) return toHex(mixed);
  }
  return toHex(target);
}

export function brandPalette(color: string): CSSProperties {
  const rgb = parse(color);
  if (!rgb) return { "--portal-color": color } as CSSProperties;
  return {
    "--portal-color": toHex(rgb),
    // White on the button unless the color is too light to carry it; then the ink.
    "--portal-on": contrast(rgb, WHITE) >= 3 ? "#ffffff" : INK,
    "--portal-text-light": readableOn(rgb, WHITE, BLACK),
    "--portal-text-dark": readableOn(rgb, DARK_SURFACE, WHITE),
  } as CSSProperties;
}
