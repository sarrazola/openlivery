"use client";

import { CSSProperties } from "react";
import { useT } from "@/lib/i18n";

// Placeholders shown while a section has not loaded yet. They exist so a genuine
// empty state ("Create your first client") never flashes before the data arrives.
// Each one mirrors the markup and geometry of what replaces it, so nothing jumps.
// Visible text is deliberately absent: the language is applied on mount, so any
// translated string here would flash in English first. Screen readers get the
// label through aria instead.

export function Skeleton({ className = "", style }: { className?: string; style?: CSSProperties }) {
  return <span className={`sk ${className}`} style={style} />;
}

function Busy({ className = "", children }: { className?: string; children: React.ReactNode }) {
  const t = useT();
  return <div className={className} role="status" aria-busy="true" aria-label={t("common.loadingContent")}>{children}</div>;
}

export function TableSkeleton({ columns, rows = 6 }: { columns: number; rows?: number }) {
  return <Busy className="table-shell"><table className="data-table"><thead><tr>{Array.from({ length: columns }).map((_, i) => <th key={i}><span className="sk sk-line sm" style={{ width: i === 0 ? 120 : 70 }} /></th>)}</tr></thead><tbody>{Array.from({ length: rows }).map((_, r) => <tr key={r}>{Array.from({ length: columns }).map((_, c) => <td key={c}>{c === 0 ? <span className="sk-row"><span className="sk sk-avatar" /><span className="sk-stack" style={{ flex: 1 }}><span className="sk sk-line" style={{ width: "45%" }} /><span className="sk sk-line sm" style={{ width: "30%" }} /></span></span> : <span className="sk sk-line" style={{ width: c === columns - 1 ? 60 : "70%" }} />}</td>)}</tr>)}</tbody></table></Busy>;
}

export function ListRowsSkeleton({ rows = 6, className = "" }: { rows?: number; className?: string }) {
  return <Busy className={`sk-rows ${className}`}>{Array.from({ length: rows }).map((_, i) => <div className="sk-row" key={i}><span className="sk sk-avatar" /><span className="sk-stack" style={{ flex: 1 }}><span className="sk sk-line" style={{ width: "38%" }} /><span className="sk sk-line sm" style={{ width: "62%" }} /></span><span className="sk sk-pill" /></div>)}</Busy>;
}

export function PanelSkeleton({ rows = 3, slim = false }: { rows?: number; slim?: boolean }) {
  return <Busy className={`sk-panel ${slim ? "slim" : ""}`}>{Array.from({ length: rows }).map((_, i) => <span className="sk sk-line" key={i} style={{ width: `${Math.max(30, 88 - i * 18)}%` }} />)}</Busy>;
}

export function FormSkeleton({ sections = 2, fields = 3 }: { sections?: number; fields?: number }) {
  return <Busy className="sk-form">{Array.from({ length: sections }).map((_, s) => <section className="form-section" key={s}><div className="section-copy"><span className="sk sk-line lg" style={{ width: 150 }} /><span className="sk sk-line sm" style={{ width: 220, marginTop: 10 }} /></div><div className="form-fields sk-stack" style={{ gap: 16 }}>{Array.from({ length: fields }).map((_, f) => <span className="sk" key={f} style={{ height: 40, borderRadius: 9 }} />)}</div></section>)}</Busy>;
}
