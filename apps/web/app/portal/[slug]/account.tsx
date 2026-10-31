"use client";

import { useEffect, useState } from "react";
import { BellRing, CircleDot } from "lucide-react";
import { UserMenu, UserMenuItems } from "@/components/user-menu";
import { useLanguage } from "@/lib/i18n";
import { disablePush, enablePush, pushConfig, pushState, type PushState, type WebPushConfig } from "@/lib/web-push";

type Availability = "online" | "away";
type AccountProps = {
  slug: string;
  name: string;
  email?: string | null;
  // Absent on a session with no person behind it: nothing to route to.
  availability?: Availability;
  onAvailability: () => void;
  onLogout: () => void;
};

/** The portal person's own menu, at the foot of the side nav: the agency's
 * menu (language, appearance, sign out) plus whether conversations are routed
 * to them, and browser notifications when the server can send them. */
export function PortalAccountMenu({ slug, name, email, availability, onAvailability, onLogout }: AccountProps) {
  return <UserMenu name={name} detail={email} status={availability} onLogout={onLogout}
    top={availability && <AvailabilityRow availability={availability} onToggle={onAvailability} />}>
    <NotificationsRow slug={slug} />
  </UserMenu>;
}

/** The same menu laid out in the page, for a phone, whose bottom bar has no
 * room for it, and for someone whose Settings would otherwise be empty. */
export function PortalAccountPanel({ slug, name, email, availability, onAvailability, onLogout }: AccountProps) {
  return <div className="user-menu inline">
    <div className="user-menu-head"><strong>{name}</strong>{email && <span>{email}</span>}</div>
    <UserMenuItems onLogout={onLogout} top={availability && <AvailabilityRow availability={availability} onToggle={onAvailability} />}>
      <NotificationsRow slug={slug} />
    </UserMenuItems>
  </div>;
}

function AvailabilityRow({ availability, onToggle }: { availability: Availability; onToggle: () => void }) {
  const { t } = useLanguage();
  const on = availability === "online";
  return <button type="button" role="switch" aria-checked={on} className="user-menu-row user-menu-toggle" onClick={onToggle}
    title={on ? t("portal.availability.setAway") : t("portal.availability.setOnline")}>
    <span><CircleDot size={17} className={`availability-icon ${availability}`} /> {on ? t("portal.availability.online") : t("portal.availability.away")}</span>
    <span className={`menu-switch${on ? " on" : ""}`} aria-hidden="true"><b /></span>
  </button>;
}

// Browser notifications for this person on this browser. Hidden while the
// server cannot send to browsers (see lib/web-push.ts), disabled when this
// browser cannot receive, with the reason underneath.
function NotificationsRow({ slug }: { slug: string }) {
  const { t } = useLanguage();
  const [config, setConfig] = useState<WebPushConfig | null>(null);
  const [state, setState] = useState<PushState>("off");
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let alive = true;
    pushConfig(slug).then(async (loaded) => {
      const current = await pushState(slug, loaded);
      if (!alive) return;
      setConfig(loaded); setState(current);
    });
    return () => { alive = false; };
  }, [slug]);
  if (!config || state === "unavailable") return null;
  const blocked = state === "unsupported" || state === "denied";
  const on = state === "on";
  async function toggle() {
    setBusy(true); setFailed(false);
    try {
      setState(on ? await disablePush(slug) : await enablePush(slug, config ?? undefined));
    } catch {
      setFailed(true);
    } finally {
      setBusy(false);
    }
  }
  const problem = state === "unsupported" ? t("settings.preferences.notificationsUnsupported")
    : state === "denied" ? t("settings.preferences.notificationsDenied")
    : failed ? t("settings.preferences.notificationsFailed")
    : null;
  return <>
    <button type="button" role="switch" aria-checked={on} className="user-menu-row user-menu-toggle" onClick={toggle} disabled={blocked || busy}
      title={on ? t("settings.preferences.notificationsOn") : t("settings.preferences.notificationsHint")}>
      <span><BellRing size={17} /> {t("settings.preferences.notifications")}</span>
      <span className={`menu-switch${on ? " on" : ""}`} aria-hidden="true"><b /></span>
    </button>
    {problem && <small className="user-menu-hint">{problem}</small>}
  </>;
}
