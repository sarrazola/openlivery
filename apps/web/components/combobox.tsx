"use client";

import { useEffect, useRef, useState } from "react";
import { Check, ChevronDown, Search } from "lucide-react";
import { useT } from "@/lib/i18n";

// Searchable dropdown (autocomplete). Used for long option lists such as the
// timezone selector and the model picker.
//   - allowCustom: also accept a value typed by the user that is not in the list
//     (e.g. a model id we don't know yet). When false it behaves as a strict
//     searchable select.
export function Combobox({
  value,
  onChange,
  options,
  placeholder,
  allowCustom = false,
  labels,
  tags,
}: {
  value: string;
  onChange: (value: string) => void;
  options: readonly string[];
  placeholder?: string;
  allowCustom?: boolean;
  /** Display text per option; the option itself is the value stored. */
  labels?: Record<string, string>;
  /** Small tag shown next to an option, e.g. "Recommended". */
  tags?: Record<string, string>;
}) {
  const t = useT();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDocument = (event: MouseEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) close();
    };
    document.addEventListener("mousedown", onDocument);
    return () => document.removeEventListener("mousedown", onDocument);
  }, [open]);

  function close() { setOpen(false); setQuery(""); }
  function pick(option: string) { onChange(option); close(); }

  const q = query.trim().toLowerCase();
  const filtered = q ? options.filter((option) => option.toLowerCase().includes(q) || (labels?.[option] ?? "").toLowerCase().includes(q)) : options;
  const canUseCustom = allowCustom && q.length > 0 && !options.some((option) => option.toLowerCase() === q);

  return (
    <div className={`combo ${open ? "open" : ""}`} ref={ref}>
      <button
        type="button"
        className="combo-value"
        onMouseDown={(event) => { event.preventDefault(); if (open) close(); else setOpen(true); }}
        onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); if (open) close(); else setOpen(true); } }}
      >
        <span className={value ? "" : "muted"}>{value ? <>{labels?.[value] ?? value}{tags?.[value] && <em className="combo-tag">{tags[value]}</em>}</> : placeholder}</span>
        <ChevronDown size={16} />
      </button>
      {open && (
        <div className="combo-pop">
          <div className="combo-search">
            <Search size={14} />
            <input
              autoFocus
              value={query}
              placeholder={t("common.search")}
              onChange={(event) => setQuery(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Escape") close();
                if (event.key === "Enter" && canUseCustom) { event.preventDefault(); pick(query.trim()); }
              }}
            />
          </div>
          <ul className="combo-list" role="listbox">
            {canUseCustom && (
              <li>
                <button type="button" className="combo-custom" onClick={() => pick(query.trim())}>
                  {t("common.useValue", { value: query.trim() })}
                </button>
              </li>
            )}
            {filtered.map((option) => (
              <li key={option}>
                <button type="button" className={option === value ? "active" : ""} onClick={() => pick(option)}>
                  <span className="combo-option">{labels?.[option] ?? option}{labels?.[option] && <code>{option}</code>}{tags?.[option] && <em className="combo-tag">{tags[option]}</em>}</span>{option === value && <Check size={14} />}
                </button>
              </li>
            ))}
            {!filtered.length && !canUseCustom && <li className="combo-empty">{t("common.noResults")}</li>}
          </ul>
        </div>
      )}
    </div>
  );
}
