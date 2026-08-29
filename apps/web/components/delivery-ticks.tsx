"use client";

import { AlertCircle, Check, CheckCheck } from "lucide-react";
import { useT } from "@/lib/i18n";

/** The ticks WhatsApp users know: one when sent, two when delivered, two in
 *  blue once read, and a warning when Meta could not deliver. */
export function DeliveryTicks({ status, error }: { status?: string | null; error?: string | null }) {
  const t = useT();
  if (!status) return null;
  if (status === "failed") return <span className="ticks failed" title={error || t("chat.delivery.failed")}><AlertCircle size={12} /></span>;
  if (status === "sent") return <span className="ticks" title={t("chat.delivery.sent")}><Check size={13} /></span>;
  return <span className={`ticks ${status === "read" ? "read" : ""}`} title={status === "read" ? t("chat.delivery.read") : t("chat.delivery.delivered")}><CheckCheck size={13} /></span>;
}
