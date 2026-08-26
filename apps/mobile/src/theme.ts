/**
 * The app is white label: the agency's colour arrives with the session and
 * drives the interface, so the same binary looks like whichever agency the
 * person belongs to. Everything else is a neutral palette that reads well
 * against any brand colour.
 */

export const palette = {
  ink: "#17213b",
  muted: "#68718a",
  subtle: "#929ab0",
  line: "#e4e8f0",
  surface: "#ffffff",
  canvas: "#f6f7fb",
  danger: "#d95757",
  bubbleIn: "#eef1f7",
};

/** Readable text colour for a filled brand-coloured surface. */
export function contrastOn(hex: string): string {
  const value = (hex || "").replace("#", "");
  if (value.length !== 6) return "#ffffff";
  const r = parseInt(value.slice(0, 2), 16);
  const g = parseInt(value.slice(2, 4), 16);
  const b = parseInt(value.slice(4, 6), 16);
  // Perceived luminance: green dominates what the eye reads as brightness.
  const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
  return luminance > 0.6 ? palette.ink : "#ffffff";
}

/** A translucent wash of the brand colour, for selected rows and soft chips. */
export function tint(hex: string, alpha = 0.12): string {
  const value = (hex || "").replace("#", "");
  if (value.length !== 6) return `rgba(7, 89, 133, ${alpha})`;
  const r = parseInt(value.slice(0, 2), 16);
  const g = parseInt(value.slice(2, 4), 16);
  const b = parseInt(value.slice(4, 6), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

export const DEFAULT_BRAND = "#075985";
