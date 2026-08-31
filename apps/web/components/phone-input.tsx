"use client";

import { useMemo, useState } from "react";
import { COUNTRIES, countryName, defaultCountry, dialCodeOf, flagOf, splitPhone } from "@/lib/dial-codes";

/** Country picker plus national number, stored the way WhatsApp keys people:
 * dial code and digits, nothing else. Whatever gets typed or pasted is
 * stripped to digits, so spaces, dashes and dots never reach the backend. */
export function PhoneInput({
  name,
  initial,
  locale,
  required,
  placeholder,
}: {
  name: string;
  initial?: string | null;
  locale: string;
  required?: boolean;
  placeholder?: string;
}) {
  const parsed = useMemo(() => splitPhone((initial || "").replace(/[^0-9]/g, "")), [initial]);
  const [iso, setIso] = useState(parsed?.iso ?? defaultCountry());
  const [national, setNational] = useState(parsed?.national ?? "");
  const options = useMemo(
    () =>
      COUNTRIES.map((entry) => ({ ...entry, label: countryName(entry.iso, locale) })).sort((a, b) =>
        a.label.localeCompare(b.label, locale)
      ),
    [locale]
  );
  const dial = dialCodeOf(iso);
  return (
    <span className="phone-input">
      <select
        aria-label={countryName(iso, locale)}
        value={iso}
        onChange={(event) => setIso(event.target.value)}
      >
        {options.map((entry) => (
          <option key={entry.iso} value={entry.iso}>
            {flagOf(entry.iso)} {entry.label} (+{entry.code})
          </option>
        ))}
      </select>
      <span className="phone-dial">+{dial}</span>
      <input
        inputMode="tel"
        autoComplete="tel-national"
        required={required}
        value={national}
        placeholder={placeholder}
        onChange={(event) => setNational(event.target.value.replace(/[^0-9]/g, ""))}
      />
      <input type="hidden" name={name} value={national ? dial + national : ""} />
    </span>
  );
}
