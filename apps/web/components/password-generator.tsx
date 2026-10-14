"use client";

import { useState } from "react";
import { Check, Copy, Sparkles } from "lucide-react";
import { useToast } from "@/components/toast";
import { useT } from "@/lib/i18n";
import { generatePassword } from "@/lib/password";

/** "Generate password" for a form that sets someone else's password: it hands
 * a strong password to the form (which fills its fields with it) and, once
 * there is one, offers to copy it so it can be passed on. */
export function PasswordGenerator({ value, onGenerate }: { value: string; onGenerate: (password: string) => void }) {
  const t = useT();
  const toast = useToast();
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      toast.success(t("common.passwordCopied"));
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      toast.error(t("common.passwordCopyFailed"));
    }
  }

  return (
    <div className="password-generator">
      <button type="button" className="button ghost small" onClick={() => { onGenerate(generatePassword()); setCopied(false); }}><Sparkles size={15} /> {t("common.generatePassword")}</button>
      {value && <button type="button" className="button ghost small" onClick={copy}>{copied ? <Check size={15} /> : <Copy size={15} />} {t(copied ? "common.copied" : "common.copyPassword")}</button>}
    </div>
  );
}
