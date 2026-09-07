import type { ReportFilters } from "./api";
import type { WorkspaceStrings } from "./workspaceStrings";

function localISO(date: Date): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

/** The API groups local days using JavaScript's positive-west offset. */
export function reportRange(days: 7 | 30, today = new Date()): ReportFilters {
  const start = new Date(today);
  start.setDate(start.getDate() - days + 1);
  return { from: localISO(start), to: localISO(today), tz_offset: today.getTimezoneOffset() };
}

export function formatDuration(seconds: number | null, s: Pick<WorkspaceStrings, "noData" | "seconds" | "minutes" | "hours">): string {
  if (seconds === null || !Number.isFinite(seconds)) return s.noData;
  const value = Math.max(0, Math.round(seconds));
  if (value < 60) return `${value} ${s.seconds}`;
  const minutes = Math.round(value / 60);
  if (minutes < 60) return `${minutes} ${s.minutes}`;
  const hours = Math.floor(minutes / 60);
  return `${hours} ${s.hours}${minutes % 60 ? ` ${minutes % 60} ${s.minutes}` : ""}`;
}
