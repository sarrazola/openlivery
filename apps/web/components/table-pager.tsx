"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";
import { useT } from "@/lib/i18n";

export const PAGE_SIZES = [5, 10, 25, 50] as const;
export const DEFAULT_PAGE_SIZE = 5;

/** The foot of a list paged in the browser: what the list holds on the
 * left (`label`, e.g. "12 agents"); rows per page, the page out of the total
 * and a step back and forward on the right. The parent owns the page and the
 * size, and slices its rows with `pageSlice`. */
export function TablePager({ label, total, page, pageSize, onPage, onPageSize }: { label: string; total: number; page: number; pageSize: number; onPage: (page: number) => void; onPageSize: (size: number) => void }) {
  const t = useT();
  const pages = Math.max(1, Math.ceil(total / pageSize));
  return <div className="table-pager">
    <span className="table-pager-label">{label}</span>
    <div className="table-pager-controls">
      <select aria-label={t("common.rowsPerPage")} title={t("common.rowsPerPage")} value={pageSize} onChange={(event) => onPageSize(Number(event.target.value))}>{PAGE_SIZES.map((size) => <option key={size} value={size}>{size}</option>)}</select>
      <span className="table-pager-page">{t("common.pageOf", { page: page + 1, pages })}</span>
      <button type="button" onClick={() => onPage(Math.max(0, page - 1))} disabled={page === 0} aria-label={t("common.previous")} title={t("common.previous")}><ChevronLeft size={16} /></button>
      <button type="button" onClick={() => onPage(Math.min(pages - 1, page + 1))} disabled={page >= pages - 1} aria-label={t("common.next")} title={t("common.next")}><ChevronRight size={16} /></button>
    </div>
  </div>;
}

export function pageSlice<T>(rows: T[], page: number, pageSize: number): T[] {
  return rows.slice(page * pageSize, (page + 1) * pageSize);
}
