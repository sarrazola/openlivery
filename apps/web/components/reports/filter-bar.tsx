"use client";

// The controls every report shares: compact selectors of one height in a
// row, the period among them, and a search box where the tab has one. Each
// tab composes the same pieces, so the bar reads the same whichever is open.

import { useState, type ReactNode } from "react";
import { CalendarDays } from "lucide-react";
import { DateRangeModal, formatRange } from "@/components/reports/date-range-modal";
import { useLanguage } from "@/lib/i18n";

export function ReportControls({ children }: { children: ReactNode }) {
  return <div className="report-controls">{children}</div>;
}

export function ControlsRow({ children }: { children: ReactNode }) {
  return <div className="report-controls-row">{children}</div>;
}

export function FilterSelect({ label, value, onChange, children, wide = false }: {
  label: string; value: string; onChange: (value: string) => void; children: ReactNode; wide?: boolean;
}) {
  return <select className={`report-select${value ? " active" : ""}${wide ? " wide" : ""}`} aria-label={label} value={value} onChange={(e) => onChange(e.target.value)}>
    {children}
  </select>;
}

// The period: presets in a select, and "custom" opening the calendar. While
// a custom range is on, a button beside the select names it and reopens the
// calendar; cancelling the calendar leaves the previous choice in place.
export function PeriodControl({ value, presets, onChange, custom, onCustom, max }: {
  value: string;
  presets: { value: string; label: string }[];
  onChange: (value: string) => void;
  custom: { from: string; to: string };
  onCustom: (from: string, to: string) => void;
  max: string;
}) {
  const { t, lang } = useLanguage();
  const locale = lang === "es" ? "es" : "en";
  const [open, setOpen] = useState(false);
  return <>
    <FilterSelect label={t("reports.explorer.period")} value={value} onChange={(v) => { if (v === "custom") setOpen(true); else onChange(v); }}>
      {presets.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
      <option value="custom">{t("reports.filters.custom")}</option>
    </FilterSelect>
    {value === "custom" && <button type="button" className="period-custom" onClick={() => setOpen(true)}>
      <CalendarDays size={15} /> {formatRange(custom.from, custom.to, locale, t("reports.filters.to"))}
    </button>}
    <DateRangeModal open={open} from={custom.from} to={custom.to} max={max} onClose={() => setOpen(false)}
      onApply={(from, to) => { onCustom(from, to); onChange("custom"); setOpen(false); }} />
  </>;
}

export function Segmented<T extends string | number>({ value, options, onChange, label }: {
  value: T;
  options: { value: T; label: string }[];
  onChange: (value: T) => void;
  label?: string;
}) {
  return <div className="segmented" role="group" aria-label={label}>
    {options.map((option) => <button key={String(option.value)} type="button" className={option.value === value ? "active" : ""} aria-pressed={option.value === value} onClick={() => onChange(option.value)}>{option.label}</button>)}
  </div>;
}
