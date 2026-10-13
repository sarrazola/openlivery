"use client";

import { useT } from "@/lib/i18n";
import type { ScheduleSlot } from "@/types";

/** Monday first, as the server numbers them (0 to 6). */
const DAYS = [0, 1, 2, 3, 4, 5, 6];
const DEFAULT_SLOT = { start: "09:00", end: "18:00" };

const minutesOf = (value: string): number => {
  const [h, m] = value.split(":").map(Number);
  return h * 60 + m;
};

/** Weekday names in the UI language; 2024-01-01 is a Monday. */
export function weekdayNames(locale: string): string[] {
  return DAYS.map((i) => new Date(2024, 0, 1 + i).toLocaleDateString(locale, { weekday: "long" }));
}

/** Whether the schedule has the agent on duty right now, read in the
 * client's timezone, the way the server reads it before answering. */
export function onDutyNow(agent: { schedule_enabled: boolean; schedule_slots: ScheduleSlot[]; client?: { timezone?: string } }): boolean {
  if (!agent.schedule_enabled) return true;
  let local: Date;
  try {
    local = new Date(new Date().toLocaleString("en-US", { timeZone: agent.client?.timezone || "UTC" }));
  } catch {
    local = new Date();
  }
  const day = (local.getDay() + 6) % 7;
  const minute = local.getHours() * 60 + local.getMinutes();
  return agent.schedule_slots.some((slot) => slot.day === day && minutesOf(slot.start) <= minute && minute < minutesOf(slot.end));
}

/** One row per weekday: on or off, and the hours it covers. Several slots a
 * day can be stored through the API; the editor shows the first and saves
 * one, so the form stays a week at a glance. */
export function AgentScheduleEditor({ enabled, slots, timezone, locale, onChange }: {
  enabled: boolean;
  slots: ScheduleSlot[];
  timezone: string;
  locale: string;
  onChange: (next: { enabled: boolean; slots: ScheduleSlot[] }) => void;
}) {
  const t = useT();
  const names = weekdayNames(locale);
  const byDay = new Map<number, ScheduleSlot>();
  for (const slot of slots) if (!byDay.has(slot.day)) byDay.set(slot.day, slot);

  const setDay = (day: number, next: ScheduleSlot | null) => {
    const rest = slots.filter((slot) => slot.day !== day);
    onChange({ enabled, slots: [...rest, ...(next ? [next] : [])].sort((a, b) => a.day - b.day) });
  };

  return (
    <section className="settings-section"><div className="settings-copy"><h3>{t("agents.detail.scheduleHeading")}</h3><p>{t("agents.detail.scheduleCopy")}</p></div><div className="settings-fields">
      <label className="switch-row"><span><strong>{t("agents.detail.scheduleToggle")}</strong><small>{t("agents.detail.scheduleToggleHint")}</small></span><input type="checkbox" checked={enabled} onChange={(e) => onChange({ enabled: e.target.checked, slots })} /></label>
      {enabled && (
        <div className="schedule-week">
          {DAYS.map((day) => {
            const slot = byDay.get(day);
            return (
              <div className={slot ? "schedule-day on" : "schedule-day"} key={day}>
                <label className="schedule-day-name"><input type="checkbox" checked={Boolean(slot)} onChange={(e) => setDay(day, e.target.checked ? { day, ...DEFAULT_SLOT } : null)} /><span>{names[day]}</span></label>
                {slot && (
                  <div className="schedule-hours">
                    <span>{t("agents.detail.scheduleFrom")}</span>
                    <input type="time" value={slot.start} required onChange={(e) => setDay(day, { ...slot, start: e.target.value })} />
                    <span>{t("agents.detail.scheduleTo")}</span>
                    <input type="time" value={slot.end === "24:00" ? "23:59" : slot.end} required min={slot.start} onChange={(e) => setDay(day, { ...slot, end: e.target.value === "23:59" ? "24:00" : e.target.value })} />
                  </div>
                )}
              </div>
            );
          })}
          <span className="field-help">{t("agents.detail.scheduleTimezone", { zone: timezone })}</span>
          {slots.length === 0 && <span className="field-help schedule-warning">{t("agents.detail.scheduleNoDays")}</span>}
        </div>
      )}
    </div></section>
  );
}
