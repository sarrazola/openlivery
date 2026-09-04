"use client";

import { InputHTMLAttributes, useState } from "react";
import { Eye, EyeOff } from "lucide-react";
import { useT } from "@/lib/i18n";

// A password field with a show/hide toggle. Drop-in for <input type="password">:
// every other prop passes through, so forms keep reading it by name.
export function PasswordInput(props: Omit<InputHTMLAttributes<HTMLInputElement>, "type">) {
  const t = useT();
  const [reveal, setReveal] = useState(false);
  return (
    <span className="secret-input">
      <input {...props} type={reveal ? "text" : "password"} />
      <button type="button" className="reveal" onClick={() => setReveal((v) => !v)} aria-pressed={reveal} aria-label={t(reveal ? "auth.hidePassword" : "auth.showPassword")}>
        {reveal ? <EyeOff size={16} /> : <Eye size={16} />}
      </button>
    </span>
  );
}
