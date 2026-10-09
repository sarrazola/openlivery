"use client";

import type { ReactNode } from "react";
import { Copy, ExternalLink, Phone, Reply } from "lucide-react";
import { useT } from "@/lib/i18n";
import type { MessageButton } from "@/types";

const ICONS: Record<string, ReactNode> = {
  QUICK_REPLY: <Reply size={12} />,
  URL: <ExternalLink size={12} />,
  PHONE_NUMBER: <Phone size={12} />,
  COPY_CODE: <Copy size={12} />,
};

/** The buttons a template message carried, under its bubble, the way the
 * templates list shows them. A record of what the person could tap, not
 * controls: the tap itself comes back as their message. */
export function MessageButtons({ buttons }: { buttons?: MessageButton[] | null }) {
  const t = useT();
  if (!buttons?.length) return null;
  return <div className="msg-buttons">
    {buttons.map((button, index) => <span key={index} className="mini-badge team">{ICONS[button.type]}{button.type === "COPY_CODE" ? t("portal.templates.form.buttonCopyCode") : button.text}</span>)}
  </div>;
}
