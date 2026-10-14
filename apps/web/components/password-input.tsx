"use client";

import { InputHTMLAttributes, useEffect, useState } from "react";
import { Eye, EyeOff } from "lucide-react";
import { useT } from "@/lib/i18n";

// A password field with a show/hide toggle. Drop-in for <input type="password">:
// every other prop passes through, so forms keep reading it by name.
// `revealed` shows the value when it turns true (a generated password).
export function PasswordInput({ revealed, ...props }: Omit<InputHTMLAttributes<HTMLInputElement>, "type"> & { revealed?: boolean }) {
  const t = useT();
  const [reveal, setReveal] = useState(false);
  useEffect(() => { if (revealed) setReveal(true); }, [revealed]);
  return (
    <span className="secret-input">
      <input {...props} type={reveal ? "text" : "password"} />
      <button type="button" className="reveal" onClick={() => setReveal((v) => !v)} aria-pressed={reveal} aria-label={t(reveal ? "auth.hidePassword" : "auth.showPassword")}>
        {reveal ? <EyeOff size={16} /> : <Eye size={16} />}
      </button>
    </span>
  );
}
