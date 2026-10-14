"use client";

import { useState } from "react";
import { Check, Copy, Dices } from "lucide-react";
import { useToast } from "@/components/toast";
import { useT } from "@/lib/i18n";
import { generatePassword } from "@/lib/password";

/** The clipboard API, and the older selection copy where a host denies it
 * (embedded views, a permissions policy). */
async function writeClipboard(text: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(text);
    return;
  } catch {
    const area = document.createElement("textarea");
    area.value = text;
    area.setAttribute("readonly", "");
    area.style.position = "fixed";
    area.style.opacity = "0";
    document.body.appendChild(area);
    area.select();
    const ok = document.execCommand("copy");
    area.remove();
    if (!ok) throw new Error("copy refused");
  }
}

/** "Generate password" for a form that sets someone else's password: it hands
 * a strong password to the form (which fills its fields with it) and, once
 * there is one, offers to copy it so it can be passed on. */
export function PasswordGenerator({ value, onGenerate }: { value: string; onGenerate: (password: string) => void }) {
  const t = useT();
  const toast = useToast();
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await writeClipboard(value);
      setCopied(true);
      toast.success(t("common.passwordCopied"));
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      toast.error(t("common.passwordCopyFailed"));
    }
  }

  return (
    <div className="password-generator">
      <button type="button" className="button ghost small" onClick={() => { onGenerate(generatePassword()); setCopied(false); }}><Dices size={15} /> {t("common.generatePassword")}</button>
      {value && <button type="button" className="button ghost small" onClick={copy}>{copied ? <Check size={15} /> : <Copy size={15} />} {t(copied ? "common.copied" : "common.copyPassword")}</button>}
    </div>
  );
}
