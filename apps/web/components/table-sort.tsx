"use client";

import { useState } from "react";
import { ArrowDown, ArrowUp, ChevronsUpDown } from "lucide-react";
import { DEFAULT_PAGE_SIZE, pageSlice } from "@/components/table-pager";
import { useT } from "@/lib/i18n";

export type SortOrder = "asc" | "desc";
export type Sort<K extends string> = { key: K; order: SortOrder };
type Cell = string | number | null | undefined;

/** A column header that orders its table. The first click sorts the way the
 * column reads best (`descending`: newest, largest; otherwise A to Z), the
 * next one reverses it. */
export function SortHeader<K extends string>({ column, label, sort, onSort, descending = false, className }: { column: K; label: string; sort: Sort<K>; onSort: (next: Sort<K>) => void; descending?: boolean; className?: string }) {
  const t = useT();
  const active = sort.key === column;
  const order: SortOrder = active ? (sort.order === "asc" ? "desc" : "asc") : descending ? "desc" : "asc";
  const Icon = !active ? ChevronsUpDown : sort.order === "asc" ? ArrowUp : ArrowDown;
  return <th className={className} aria-sort={active ? (sort.order === "asc" ? "ascending" : "descending") : "none"}>
    <button type="button" className={`sort-header${active ? " active" : ""}`} onClick={() => onSort({ key: column, order })} title={t("common.sortBy", { column: label })}>
      {label}<Icon size={13} aria-hidden />
    </button>
  </th>;
}

/** Rows ordered by one column; empty cells go last whichever the order. */
export function sortRows<T>(rows: T[], value: (row: T) => Cell, order: SortOrder): T[] {
  const sign = order === "asc" ? 1 : -1;
  const empty = (cell: Cell) => cell == null || cell === "";
  return [...rows].sort((a, b) => {
    const x = value(a), y = value(b);
    if (empty(x) || empty(y)) return empty(x) === empty(y) ? 0 : empty(x) ? 1 : -1;
    if (typeof x === "number" && typeof y === "number") return (x - y) * sign;
    return String(x).localeCompare(String(y), undefined, { numeric: true, sensitivity: "base" }) * sign;
  });
}

/** Order and page a list held in the browser. `value` reads the cell a row
 * is ordered by; ordering or resizing goes back to the first page. */
export function useTableView<T, K extends string>(rows: T[], value: (row: T, key: K) => Cell, initial: Sort<K>) {
  const [sort, setSort] = useState(initial);
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState<number>(DEFAULT_PAGE_SIZE);
  // A refresh can shorten the list under the page being read.
  const current = Math.min(page, Math.max(0, Math.ceil(rows.length / pageSize) - 1));
  return {
    rows: pageSlice(sortRows(rows, (row) => value(row, sort.key), sort.order), current, pageSize),
    total: rows.length,
    sort,
    page: current,
    pageSize,
    onSort: (next: Sort<K>) => { setSort(next); setPage(0); },
    onPage: setPage,
    onPageSize: (size: number) => { setPageSize(size); setPage(0); },
  };
}
