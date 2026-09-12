import type { CSSProperties } from "react";

// The presets a tag color picker offers. Any #rrggbb is accepted by the API;
// these are the ones a click away, in the same order the API rotates through.
export const TAG_PALETTE: { value: string; name: string }[] = [
  { value: "#6b7280", name: "gray" }, { value: "#3b82f6", name: "blue" }, { value: "#22c55e", name: "green" }, { value: "#f59e0b", name: "amber" },
  { value: "#ef4444", name: "red" }, { value: "#8b5cf6", name: "violet" }, { value: "#ec4899", name: "pink" }, { value: "#14b8a6", name: "teal" },
  { value: "#f97316", name: "orange" }, { value: "#84cc16", name: "lime" }, { value: "#06b6d4", name: "cyan" }, { value: "#6366f1", name: "indigo" },
  { value: "#a855f7", name: "purple" }, { value: "#f43f5e", name: "rose" }, { value: "#0ea5e9", name: "sky" }, { value: "#10b981", name: "emerald" },
];

// Tags saved before colors were hex carry a palette name; paint those as before.
const LEGACY: Record<string, string> = Object.fromEntries(TAG_PALETTE.slice(0, 8).map((item) => [item.name, item.value]));

export function tagColor(color: string | null | undefined): string {
  if (!color) return TAG_PALETTE[0].value;
  return color.startsWith("#") ? color : LEGACY[color] ?? TAG_PALETTE[0].value;
}

/** The style that tints a chip, dot or swatch: the CSS reads `--tag`. */
export function tagStyle(color: string | null | undefined): CSSProperties {
  return { "--tag": tagColor(color) } as CSSProperties;
}
