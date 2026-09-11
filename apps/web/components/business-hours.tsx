"use client";

import { Plus, X } from "lucide-react";
import { useT } from "@/lib/i18n";

export type Range = [string, string];
export type Mode = "off" | "always" | "custom";
export type Hours = { mode: Mode; days: Range[][]; note: string };

const MODES: Mode[] = ["off", "always", "custom"];
const WEEKDAY_KEYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"] as const;

export const EMPTY_HOURS: Hours = {
  mode: "off",
  days: [...Array(5)].map(() => [["09:00", "18:00"] as Range]).concat([[], []]),
  note: "",
};

/** Accept whatever the API returns and make it safe to render. */
export function normalizeHours(value: unknown): Hours {
  const raw = (value || {}) as Partial<Hours>;
  const days =
    Array.isArray(raw.days) && raw.days.length === 7
      ? raw.days.map((day) => (Array.isArray(day) ? day.filter((range) => Array.isArray(range) && range.length === 2) : []))
      : EMPTY_HOURS.days;
  const mode: Mode = raw.mode === "always" || raw.mode === "custom" ? raw.mode : "off";
  return { mode, days: days as Range[][], note: raw.note || "" };
}

/**
 * When the business is open, so the agent never promises attention nobody
 * will give. "No hours" means they are not written here, not that the
 * business has none: a tool that can look them up still answers.
 */
export function BusinessHoursEditor({ value, onChange }: { value: Hours; onChange: (hours: Hours) => void }) {
  const t = useT();
  const set = (patch: Partial<Hours>) => onChange({ ...value, ...patch });

  function editDay(index: number, ranges: Range[]) {
    set({ days: value.days.map((day, i) => (i === index ? ranges : day)) });
  }

  return (
    <div className="bh">
      <div className="bh-modes">
        {MODES.map((mode) => (
          <button key={mode} type="button" className={value.mode === mode ? "active" : ""} onClick={() => set({ mode })}>
            <strong>{t(`agents.hours.mode.${mode}.label`)}</strong>
            <small>{t(`agents.hours.mode.${mode}.hint`)}</small>
          </button>
        ))}
      </div>

      {value.mode === "always" && <p className="field-help">{t("agents.hours.alwaysHelp")}</p>}

      {value.mode === "custom" && (
        <>
          <div className="bh-days">
            {WEEKDAY_KEYS.map((key, index) => {
              const ranges = value.days[index] || [];
              const open = ranges.length > 0;
              return (
                <div key={key} className={`bh-day ${open ? "" : "bh-closed"}`}>
                  <label className="bh-name">
                    <input
                      type="checkbox"
                      checked={open}
                      onChange={(event) => editDay(index, event.target.checked ? [["09:00", "18:00"]] : [])}
                    />
                    <span>{t(`agents.hours.day.${key}`)}</span>
                  </label>

                  {open ? (
                    <div className="bh-ranges">
                      {ranges.map((range, position) => (
                        <div key={position} className="bh-range">
                          <input
                            type="time"
                            value={range[0]}
                            aria-label={t("agents.hours.from")}
                            onChange={(event) =>
                              editDay(index, ranges.map((item, i) => (i === position ? [event.target.value, item[1]] as Range : item)))
                            }
                          />
                          <span>{t("agents.hours.to")}</span>
                          <input
                            type="time"
                            value={range[1]}
                            aria-label={t("agents.hours.to")}
                            onChange={(event) =>
                              editDay(index, ranges.map((item, i) => (i === position ? [item[0], event.target.value] as Range : item)))
                            }
                          />
                          {ranges.length > 1 && (
                            <button
                              type="button"
                              className="icon-button"
                              title={t("agents.hours.removeShift")}
                              aria-label={t("agents.hours.removeShift")}
                              onClick={() => editDay(index, ranges.filter((_, i) => i !== position))}
                            >
                              <X size={14} />
                            </button>
                          )}
                        </div>
                      ))}
                      {/* Three is enough for a morning, an afternoon and an evening. */}
                      {ranges.length < 3 && (
                        <button type="button" className="bh-add" onClick={() => editDay(index, [...ranges, ["16:00", "20:00"] as Range])}>
                          <Plus size={13} /> {t("agents.hours.addShift")}
                        </button>
                      )}
                    </div>
                  ) : (
                    <span className="bh-off">{t("agents.hours.closed")}</span>
                  )}
                </div>
              );
            })}
          </div>

          <label>
            {t("agents.hours.noteLabel")}
            <input value={value.note} maxLength={400} onChange={(event) => set({ note: event.target.value })} placeholder={t("agents.hours.notePlaceholder")} />
            <span className="field-help">{t("agents.hours.noteHelp")}</span>
          </label>
        </>
      )}
    </div>
  );
}
