"use client";

import { Phone } from "lucide-react";
import { useLanguage } from "@/lib/i18n";
import type { PhoneCallInfo } from "@/types";

function minutes(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

/** Above a phone conversation's transcript: how long the call took, what
 * ElevenLabs charged and its summary, once the hang-up is reported. */
export function CallHeader({ call }: { call?: PhoneCallInfo | null }) {
  const { t } = useLanguage();
  if (!call) return null;
  return <div className="call-header">
    <div className="call-header-facts">
      <span><Phone size={13} /> <strong>{t("phone.call.title")}</strong></span>
      {call.caller && <span>{t("phone.call.caller")}: <strong>{call.caller}</strong></span>}
      {call.ended_at
        ? <>
          {call.duration_seconds != null && <span>{t("phone.call.duration")}: <strong>{minutes(call.duration_seconds)}</strong></span>}
          {call.cost_credits != null && <span>{t("phone.call.cost")}: <strong>{t("phone.call.credits", { n: call.cost_credits.toLocaleString() })}</strong></span>}
        </>
        : <span><strong>{t("phone.call.inProgress")}</strong></span>}
    </div>
    {call.summary && <p><strong>{t("phone.call.summary")}:</strong> {call.summary}</p>}
  </div>;
}
