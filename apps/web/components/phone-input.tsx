"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Search } from "lucide-react";
import { COUNTRIES, countryName, defaultCountry, dialCodeOf, flagOf, splitPhone } from "@/lib/dial-codes";

/** Country picker plus national number, stored the way WhatsApp keys people:
 * dial code and digits, nothing else. Whatever gets typed or pasted is
 * stripped to digits, so spaces, dashes and dots never reach the backend.
 * The picker opens a searchable panel; closed it shows only the flag. */
export function PhoneInput({
  name,
  initial,
  locale,
  required,
  placeholder,
  searchPlaceholder,
}: {
  name: string;
  initial?: string | null;
  locale: string;
  required?: boolean;
  placeholder?: string;
  searchPlaceholder?: string;
}) {
  const parsed = useMemo(() => splitPhone((initial || "").replace(/[^0-9]/g, "")), [initial]);
  const [iso, setIso] = useState(parsed?.iso ?? defaultCountry());
  const [national, setNational] = useState(parsed?.national ?? "");
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const wrapRef = useRef<HTMLSpanElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);

  const options = useMemo(
    () =>
      COUNTRIES.map((entry) => ({ ...entry, label: countryName(entry.iso, locale) })).sort((a, b) =>
        a.label.localeCompare(b.label, locale)
      ),
    [locale]
  );
  const term = query.trim().toLowerCase();
  const filtered = term
    ? options.filter((entry) => `${entry.label} +${entry.code}`.toLowerCase().includes(term))
    : options;

  useEffect(() => {
    if (!open) return;
    searchRef.current?.focus();
    const onPointerDown = (event: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(event.target as Node)) setOpen(false);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  const dial = dialCodeOf(iso);
  return (
    <span className="phone-input" ref={wrapRef}>
      <button
        type="button"
        className="phone-country"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={countryName(iso, locale)}
        title={countryName(iso, locale)}
        onClick={() => {
          setQuery("");
          setOpen((value) => !value);
        }}
      >
        <span aria-hidden="true">{flagOf(iso)}</span>
      </button>
      <span className="phone-field">
        <span className="phone-dial" aria-hidden="true">+{dial}</span>
        <input
          inputMode="tel"
          autoComplete="tel-national"
          required={required}
          value={national}
          placeholder={placeholder}
          onChange={(event) => setNational(event.target.value.replace(/[^0-9]/g, ""))}
        />
      </span>
      <input type="hidden" name={name} value={national ? dial + national : ""} />
      {open && (
        <span className="phone-menu">
          <span className="phone-menu-search">
            <Search size={14} />
            <input
              ref={searchRef}
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder={searchPlaceholder}
            />
          </span>
          <span className="phone-menu-list" role="listbox" aria-label={searchPlaceholder}>
            {filtered.map((entry) => (
              <button
                type="button"
                key={entry.iso}
                role="option"
                aria-selected={entry.iso === iso}
                className={entry.iso === iso ? "active" : ""}
                onClick={() => {
                  setIso(entry.iso);
                  setOpen(false);
                }}
              >
                <span aria-hidden="true">{flagOf(entry.iso)}</span>
                <span className="phone-menu-name">{entry.label}</span>
              </button>
            ))}
          </span>
        </span>
      )}
    </span>
  );
}
