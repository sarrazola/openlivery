"use client";

import { useEffect, useState } from "react";
import { BellRing, CircleDot, Info } from "lucide-react";
import { Modal } from "@/components/ui";
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
 * menu (language, appearance, sign out) plus browser notifications when the
 * server can send them and whether conversations are routed to them. The two
 * switches sit together, below the two pickers. */
export function PortalAccountMenu({ slug, name, email, availability, onAvailability, onLogout }: AccountProps) {
  const away = useAwayConfirm(availability, onAvailability);
  return <>
    <UserMenu name={name} detail={email} status={availability} onLogout={onLogout}>
      <NotificationsRow slug={slug} />
      {availability && <AvailabilityRow availability={availability} onToggle={away.toggle} />}
    </UserMenu>
    {away.modal}
  </>;
}

/** The same menu laid out in the page, for a phone, whose bottom bar has no
 * room for it, and for someone whose Settings would otherwise be empty. */
export function PortalAccountPanel({ slug, name, email, availability, onAvailability, onLogout }: AccountProps) {
  const away = useAwayConfirm(availability, onAvailability);
  return <div className="user-menu inline">
    <div className="user-menu-head"><strong>{name}</strong>{email && <span>{email}</span>}</div>
    <UserMenuItems onLogout={onLogout}>
      <NotificationsRow slug={slug} />
      {availability && <AvailabilityRow availability={availability} onToggle={away.toggle} />}
    </UserMenuItems>
    {away.modal}
  </div>;
}

// Going away changes who gets new conversations, so it is confirmed with what
// it means; coming back needs no words. The dialog lives with the menu's
// owner, not inside the menu, so it stays open when the menu closes.
function useAwayConfirm(availability: Availability | undefined, onAvailability: () => void) {
  const { t } = useLanguage();
  const [asking, setAsking] = useState(false);
  const toggle = () => { if (availability === "online") setAsking(true); else onAvailability(); };
  const confirm = () => { setAsking(false); onAvailability(); };
  const modal = <Modal open={asking} title={t("portal.availability.confirmAwayTitle")} onClose={() => setAsking(false)}>
    <div className="modal-form">
      <p className="muted">{t("portal.availability.confirmAwayCopy")}</p>
      <p className="muted">{t("portal.availability.confirmAwayKeep")}</p>
      <div className="modal-actions">
        <button type="button" className="button" onClick={() => setAsking(false)}>{t("common.cancel")}</button>
        <button type="button" className="button primary" onClick={confirm}>{t("common.ok")}</button>
      </div>
    </div>
  </Modal>;
  return { toggle, modal };
}

// A toggle row is turned by its switch alone: a click that lands on the label
// changes nothing.
function AvailabilityRow({ availability, onToggle }: { availability: Availability; onToggle: () => void }) {
  const { t } = useLanguage();
  const on = availability === "online";
  const label = on ? t("portal.availability.online") : t("portal.availability.away");
  return <div className="user-menu-row user-menu-toggle">
    <span><CircleDot size={17} className={`availability-icon ${availability}`} /> {label}</span>
    <button type="button" role="switch" aria-checked={on} aria-label={label} className={`menu-switch${on ? " on" : ""}`} onClick={onToggle}><b /></button>
  </div>;
}

// Browser notifications for this person on this browser. Hidden while the
// server cannot send to browsers (see lib/web-push.ts). When this browser
// cannot receive them, or turning them on failed, the switch (or the info mark
// beside the label) explains why in a dialog, like going away does, instead of
// a paragraph crowding the menu.
function NotificationsRow({ slug }: { slug: string }) {
  const { t } = useLanguage();
  const [config, setConfig] = useState<WebPushConfig | null>(null);
  const [state, setState] = useState<PushState>("off");
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  const [explaining, setExplaining] = useState(false);
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
    if (blocked) { setExplaining(true); return; }
    setBusy(true); setFailed(false);
    try {
      setState(on ? await disablePush(slug) : await enablePush(slug, config ?? undefined));
    } catch {
      setFailed(true); setExplaining(true);
    } finally {
      setBusy(false);
    }
  }
  const problem = state === "unsupported" ? t("settings.preferences.notificationsUnsupported")
    : state === "denied" ? t("settings.preferences.notificationsDenied")
    : failed ? t("settings.preferences.notificationsFailed")
    : null;
  return <>
    <div className="user-menu-row user-menu-toggle">
      <span><BellRing size={17} /> {t("settings.preferences.notifications")}{problem && <button type="button" className="user-menu-info" onClick={() => setExplaining(true)} aria-label={problem}><Info size={14} /></button>}</span>
      <button type="button" role="switch" aria-checked={on} aria-label={t("settings.preferences.notifications")} className={`menu-switch${on ? " on" : ""}${blocked ? " blocked" : ""}`} onClick={toggle} disabled={busy}><b /></button>
    </div>
    <Modal open={explaining && problem !== null} title={t("settings.preferences.notificationsBlockedTitle")} onClose={() => setExplaining(false)}>
      <div className="modal-form">
        <p className="muted">{problem}</p>
        {state === "denied" && <p className="muted">{t("settings.preferences.notificationsDeniedHow")}</p>}
        <div className="modal-actions"><button type="button" className="button primary" onClick={() => setExplaining(false)}>{t("common.ok")}</button></div>
      </div>
    </Modal>
  </>;
}
