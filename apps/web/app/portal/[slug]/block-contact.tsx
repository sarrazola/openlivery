"use client";

// The dialog that blocks a contact, opened from Contacts and from the thread
// header. It offers the two kinds of block and says what each does: a soft
// block is internal (messages are kept, nobody answers, the person notices
// nothing); a hard block also puts the person on WhatsApp's own block list.
// WhatsApp accepts that only for someone who wrote to a WhatsApp API number
// in the last 24 hours, so the dialog asks the API first and offers the hard
// block only when it can go through.
//
// Mount it while it is open: its state starts fresh for each contact.

import { useEffect, useState } from "react";
import { Ban, LoaderCircle } from "lucide-react";
import { Alert, Modal } from "@/components/ui";
import { api, messageFrom } from "@/lib/api";
import { useT, type I18nKey } from "@/lib/i18n";
import type { Contact } from "@/types";

type BlockOptions = { hard_available: boolean; hard_unavailable_reason: string | null };

const UNAVAILABLE: Record<string, I18nKey> = {
  no_whatsapp_api: "portal.contacts.blockHardNoWhatsapp",
  window_closed: "portal.contacts.blockHardWindow",
};

export function BlockContactModal({ slug, contactId, name, upgrade = false, onClose, onBlocked }: {
  slug: string;
  contactId: string;
  name: string;
  /** The contact is already soft-blocked: only the hard block is on offer. */
  upgrade?: boolean;
  onClose: () => void;
  onBlocked: (contact: Contact) => void;
}) {
  const t = useT();
  const [options, setOptions] = useState<BlockOptions | null>(null);
  const [hard, setHard] = useState(upgrade);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    api<BlockOptions>(`/portal/${slug}/contacts/${contactId}/block`)
      .then((found) => { if (!cancelled) setOptions(found); })
      // Without an answer the soft block still works; the hard one stays off.
      .catch(() => { if (!cancelled) setOptions({ hard_available: false, hard_unavailable_reason: null }); });
    return () => { cancelled = true; };
  }, [slug, contactId]);

  const hardAvailable = Boolean(options?.hard_available);
  const reason = options && !options.hard_available ? UNAVAILABLE[options.hard_unavailable_reason ?? ""] : undefined;
  const wantsHard = hard && hardAvailable;

  async function block() {
    setBusy(true); setError("");
    try {
      const updated = await api<Contact>(`/portal/${slug}/contacts/${contactId}/block`, { method: "POST", body: JSON.stringify({ blocked: true, hard: wantsHard }) });
      onBlocked(updated);
    } catch (err) { setError(messageFrom(err)); setBusy(false); }
  }

  return (
    <Modal open title={t(upgrade ? "portal.contacts.blockUpgradeTitle" : "portal.contacts.blockTitle", { name })} onClose={onClose}>
      <div className="modal-form">
        <div className="block-choices" role="radiogroup" aria-label={t("portal.contacts.block")}>
          {!upgrade && <button type="button" role="radio" aria-checked={!wantsHard} className={`block-choice${wantsHard ? "" : " selected"}`} onClick={() => setHard(false)}>
            <strong>{t("portal.contacts.blockSoft")}</strong>
            <span>{t("portal.contacts.blockSoftCopy")}</span>
          </button>}
          <button type="button" role="radio" aria-checked={wantsHard} disabled={!hardAvailable} className={`block-choice${wantsHard ? " selected" : ""}`} onClick={() => setHard(true)}>
            <strong>{t("portal.contacts.blockHard")}</strong>
            <span>{t("portal.contacts.blockHardCopy")}</span>
            {reason && <em>{t(reason)}</em>}
          </button>
        </div>
        <p className="modal-copy">{t("portal.contacts.blockUnblockCopy")}</p>
        {error && <Alert>{error}</Alert>}
        <div className="modal-actions">
          <button type="button" className="button" onClick={onClose}>{t("common.cancel")}</button>
          <button type="button" className="button danger" disabled={busy || !options || (upgrade && !hardAvailable)} onClick={block}>{busy ? <LoaderCircle className="spin" size={16} /> : <><Ban size={15} /> {t("portal.contacts.block")}</>}</button>
        </div>
      </div>
    </Modal>
  );
}
