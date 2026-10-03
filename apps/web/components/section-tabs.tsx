"use client";

import { ChevronLeft, ChevronRight, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

export type SectionTab<T extends string> = { id: T; label: string; icon?: LucideIcon; badge?: ReactNode };

// One tab state, two controls. The tab strip is what a desktop shows. On a
// phone four or more tabs do not fit the strip, and it scrolled sideways with
// nothing to say it did, so there the strip gives way to a pager: one section
// at a time, an arrow back and forward, and a position count. Each arrow is
// labelled with the section it leads to. The stylesheet decides which of the
// two is on screen (.section-tabs / .section-pager); the parent only owns the
// value, exactly as it did with a hand-written strip.
export function SectionTabs<T extends string>({ tabs, value, onChange, className }: { tabs: SectionTab<T>[]; value: T; onChange: (id: T) => void; className?: string }) {
  const index = Math.max(0, tabs.findIndex((tab) => tab.id === value));
  const current = tabs[index];
  const previous = index > 0 ? tabs[index - 1] : undefined;
  const next = index < tabs.length - 1 ? tabs[index + 1] : undefined;
  return (
    <>
      <nav className={`tabs section-tabs${className ? ` ${className}` : ""}`}>
        {tabs.map((tab) => (
          <button key={tab.id} type="button" data-tab={tab.id} className={tab.id === value ? "active" : ""} onClick={() => onChange(tab.id)}>
            {tab.icon && <tab.icon size={17} />} {tab.label}{tab.badge !== undefined && <> <span>{tab.badge}</span></>}
          </button>
        ))}
      </nav>
      <div className="section-pager">
        <button type="button" className="button ghost" disabled={!previous} aria-label={previous?.label} onClick={() => previous && onChange(previous.id)}><ChevronLeft size={18} /></button>
        <div className="section-pager-current">
          {current.icon && <current.icon size={17} />}<strong>{current.label}</strong>{current.badge !== undefined && <span>{current.badge}</span>}<small>{index + 1} / {tabs.length}</small>
        </div>
        <button type="button" className="button ghost" disabled={!next} aria-label={next?.label} onClick={() => next && onChange(next.id)}><ChevronRight size={18} /></button>
      </div>
    </>
  );
}
