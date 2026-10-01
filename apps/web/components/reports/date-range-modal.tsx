"use client";

// A small calendar for the reports: one month, a start and an end chosen
// by clicking, and nothing applied until the person says so. Days after
// `max` cannot be picked.

import { useEffect, useMemo, useState } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { Modal } from "@/components/ui";
import { useLanguage } from "@/lib/i18n";

export function localISO(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
function parseISO(iso: string): Date {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, (m || 1) - 1, d || 1);
}
function monthStart(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth(), 1);
}
function addMonths(d: Date, n: number): Date {
  return new Date(d.getFullYear(), d.getMonth() + n, 1);
}

export function formatRange(from: string, to: string, locale: string, joiner: string): string {
  if (!from || !to) return "";
  const a = parseISO(from);
  const b = parseISO(to);
  const sameYear = a.getFullYear() === b.getFullYear();
  const day = (d: Date, year: boolean) => d.toLocaleDateString(locale, year ? { day: "numeric", month: "short", year: "numeric" } : { day: "numeric", month: "short" });
  if (from === to) return day(a, true);
  return `${day(a, !sameYear)} ${joiner} ${day(b, true)}`;
}

export function DateRangeModal({ open, from, to, max, onApply, onClose }: {
  open: boolean; from: string; to: string; max: string; onApply: (from: string, to: string) => void; onClose: () => void;
}) {
  const { t, lang } = useLanguage();
  const locale = lang === "es" ? "es" : "en";
  const today = max || localISO(new Date());
  const [start, setStart] = useState(from);
  const [end, setEnd] = useState<string | null>(to);
  const [cursor, setCursor] = useState(() => monthStart(parseISO(to || today)));

  useEffect(() => {
    if (!open) return;
    setStart(from || today);
    setEnd(to || today);
    setCursor(monthStart(parseISO(to || today)));
  }, [open, from, to, today]);

  // Monday first; the names come from the locale.
  const weekdays = useMemo(() => Array.from({ length: 7 }, (_, i) => new Date(2024, 0, 1 + i).toLocaleDateString(locale, { weekday: "short" }).replace(".", "").slice(0, 2)), [locale]);

  const pick = (iso: string) => {
    if (iso > today) return;
    if (!start || end !== null) { setStart(iso); setEnd(null); return; }
    if (iso < start) { setEnd(start); setStart(iso); return; }
    setEnd(iso);
  };
  const effectiveEnd = end ?? start;
  const complete = Boolean(start && end);
  const dayLabel = (iso: string | null) => iso ? parseISO(iso).toLocaleDateString(locale, { day: "numeric", month: "short", year: "numeric" }) : "";
  const blanks = (cursor.getDay() + 6) % 7;
  const days = new Date(cursor.getFullYear(), cursor.getMonth() + 1, 0).getDate();

  return <Modal open={open} title={t("reports.range.title")} onClose={onClose}>
    <div className="drp">
      <div className="drp-fields">
        <div className={`drp-field${end !== null ? " next" : ""}`}><small>{t("reports.range.from")}</small><strong>{dayLabel(start)}</strong></div>
        <div className={`drp-field${end === null ? " next" : ""}`}><small>{t("reports.range.to")}</small><strong>{end ? dayLabel(end) : t("reports.range.pickEnd")}</strong></div>
      </div>
      <div className="drp-month">
        <header>
          <button type="button" onClick={() => setCursor(addMonths(cursor, -1))} aria-label={t("reports.range.prevMonth")}><ChevronLeft size={16} /></button>
          <strong>{cursor.toLocaleDateString(locale, { month: "long", year: "numeric" })}</strong>
          <button type="button" onClick={() => setCursor(addMonths(cursor, 1))} aria-label={t("reports.range.nextMonth")} disabled={localISO(addMonths(cursor, 1)) > today}><ChevronRight size={16} /></button>
        </header>
        <div className="drp-grid">
          {weekdays.map((w, i) => <span className="wd" key={i}>{w}</span>)}
          {Array.from({ length: blanks }, (_, i) => <span key={`b${i}`} />)}
          {Array.from({ length: days }, (_, i) => {
            const iso = localISO(new Date(cursor.getFullYear(), cursor.getMonth(), i + 1));
            const inRange = start && effectiveEnd && iso > start && iso < effectiveEnd;
            const cls = [iso === start ? "start" : "", iso === effectiveEnd && end !== null ? "end" : "", inRange ? "in" : "", iso === today ? "today" : ""].filter(Boolean).join(" ");
            return <button type="button" key={iso} className={cls} disabled={iso > today} onClick={() => pick(iso)} aria-pressed={iso === start || iso === effectiveEnd}>{i + 1}</button>;
          })}
        </div>
      </div>
      <div className="drp-foot">
        <button type="button" className="button secondary" onClick={onClose}>{t("reports.range.cancel")}</button>
        <button type="button" className="button primary" disabled={!complete} onClick={() => complete && onApply(start, end as string)}>{t("reports.range.apply")}</button>
      </div>
    </div>
  </Modal>;
}
