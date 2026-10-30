"use client";

import { useEffect, useState } from "react";
import { CheckCircle2, ExternalLink, LoaderCircle, Phone, Plus, Save } from "lucide-react";
import { Alert } from "@/components/ui";
import { KeyActions } from "@/components/key-actions";
import { PasswordInput } from "@/components/password-input";
import { useToast } from "@/components/toast";
import { api, messageFrom } from "@/lib/api";
import { useT, type I18nKey } from "@/lib/i18n";
import type { CallAccount, CallProvider } from "@/types";

type Field = { name: "api_key" | "account_sid" | "auth_token"; label: I18nKey; secret: boolean };
type Carrier = "twilio" | "telnyx";
const FIELDS: Record<CallProvider, Field[]> = {
  elevenlabs: [{ name: "api_key", label: "phone.settings.apiKey", secret: true }],
  twilio: [
    { name: "account_sid", label: "phone.settings.accountSid", secret: true },
    { name: "auth_token", label: "phone.settings.authToken", secret: true },
  ],
  telnyx: [{ name: "api_key", label: "phone.settings.apiKey", secret: true }],
};
// The page of each provider where the credentials asked for here are, with
// its path as the link text so it can be found by hand too.
const GUIDES: Record<CallProvider, { url: string; label: I18nKey }> = {
  elevenlabs: { url: "https://elevenlabs.io/app/settings/api-keys", label: "phone.settings.elevenlabsGuide" },
  twilio: { url: "https://console.twilio.com/", label: "phone.settings.twilioGuide" },
  telnyx: { url: "https://portal.telnyx.com/#/app/api-keys", label: "phone.settings.telnyxGuide" },
};
const CARRIERS: { id: Carrier; name: string }[] = [{ id: "twilio", name: "Twilio" }, { id: "telnyx", name: "Telnyx" }];
const nameOf = (provider: CallProvider) => provider === "elevenlabs" ? "ElevenLabs" : provider === "twilio" ? "Twilio" : "Telnyx";

/** Settings > Phone calls: the agency's ElevenLabs key and the account of the
 * phone carrier its numbers are bought from. Each is checked with the
 * provider before it is stored. */
export function PhoneAccounts() {
  const t = useT();
  const [accounts, setAccounts] = useState<CallAccount[] | null>(null);
  const load = () => api<CallAccount[]>("/phone/accounts").then(setAccounts).catch(() => setAccounts([]));
  useEffect(() => { load(); }, []);
  const stateOf = (provider: CallProvider) => accounts?.find((a) => a.provider === provider);

  return <section className="section-block"><div className="section-heading"><div><h2><Phone size={18} /> {t("phone.settings.heading")}</h2><p>{t("phone.settings.copy")}</p></div></div>
    {accounts && <>
      <section className="form-section"><div className="section-copy"><h2>{t("phone.settings.elevenlabsTitle")}</h2><p>{t("phone.settings.elevenlabsCopy")}</p></div>
        <div className="form-fields key-form"><AccountForm provider="elevenlabs" state={stateOf("elevenlabs")} onChange={load} /></div>
      </section>
      <CarrierSection stateOf={stateOf} onChange={load} />
    </>}
  </section>;
}

function GuideLink({ provider }: { provider: CallProvider }) {
  const t = useT();
  const guide = GUIDES[provider];
  return <a className="guide-link" href={guide.url} target="_blank" rel="noreferrer"><ExternalLink size={13} /> {t(guide.label)}</a>;
}

/** One carrier at a time on screen: the connected ones, each with its
 * actions, and a form whose fields follow the carrier picked in it. */
function CarrierSection({ stateOf, onChange }: { stateOf: (p: CallProvider) => CallAccount | undefined; onChange: () => void }) {
  const t = useT();
  const connected = CARRIERS.filter((c) => stateOf(c.id)?.stored);
  const [adding, setAdding] = useState(false);
  const [carrier, setCarrier] = useState<Carrier>(connected[0]?.id ?? "twilio");
  const available = CARRIERS.filter((c) => !stateOf(c.id)?.stored);
  const showForm = !connected.length || adding;

  return <section className="form-section"><div className="section-copy"><h2>{t("phone.settings.carrierTitle")}</h2><p>{t("phone.settings.carrierCopy")}</p></div>
    <div className="form-fields key-form">
      {connected.map((c) => <div key={c.id} className="carrier-connected"><AccountForm provider={c.id} state={stateOf(c.id)} onChange={onChange} /></div>)}
      {showForm && <>
        <label>{t("phone.settings.carrierLabel")}
          <select value={carrier} onChange={(event) => setCarrier(event.target.value as Carrier)}>
            {(adding ? available : CARRIERS).map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </label>
        <AccountForm key={carrier} provider={carrier} state={undefined} onChange={() => { setAdding(false); onChange(); }} onCancel={adding ? () => setAdding(false) : undefined} />
      </>}
      {!showForm && available.length > 0 && <button type="button" className="button ghost align-start" onClick={() => { setCarrier(available[0].id); setAdding(true); }}><Plus size={15} /> {t("phone.settings.addCarrier", { name: available[0].name })}</button>}
    </div>
  </section>;
}

/** The fields of one provider's account, or its connected state with the
 * actions to replace or remove it. */
function AccountForm({ provider, state, onChange, onCancel }: { provider: CallProvider; state?: CallAccount; onChange: () => void; onCancel?: () => void }) {
  const t = useT();
  const toast = useToast();
  const fields = FIELDS[provider];
  const [values, setValues] = useState<Record<string, string>>({});
  const [replacing, setReplacing] = useState(false);
  const [busy, setBusy] = useState(false);
  const stored = Boolean(state?.stored) && !replacing;
  const complete = fields.every((field) => (values[field.name] || "").trim());

  async function save() {
    setBusy(true);
    try {
      const body = JSON.stringify(Object.fromEntries(fields.map((f) => [f.name, (values[f.name] || "").trim()])));
      const test = await api<{ ok: boolean; message: string }>(`/phone/accounts/${provider}/validate`, { method: "POST", body });
      if (!test.ok) { toast.error(test.message); return; }
      await api(`/phone/accounts/${provider}`, { method: "PUT", body });
      toast.success(test.message);
      setValues({}); setReplacing(false); onChange();
    } catch (err) { toast.error(messageFrom(err)); } finally { setBusy(false); }
  }

  // Errors stay in the confirmation dialog, which shows them.
  async function remove() {
    await api(`/phone/accounts/${provider}`, { method: "DELETE" });
    toast.success(t("phone.settings.removed"));
    onChange();
  }

  if (stored) return <div className="key-configured">
    <div className="key-configured-head">
      <span className="key-configured-status"><CheckCircle2 size={18} /> {t(fields.length === 1 ? "phone.settings.keyConfigured" : "phone.settings.accountConnected", { name: nameOf(provider) })}</span>
      <KeyActions busy={busy} replaceLabel={t("phone.settings.replace")} removeLabel={t("phone.settings.remove")} confirmTitle={t("phone.settings.removeTitle", { name: nameOf(provider) })} confirmMessage={t("phone.settings.removeCopy", { name: nameOf(provider) })} onReplace={() => { setValues({}); setReplacing(true); }} onRemove={remove} />
    </div>
    {state?.last_error && <Alert>{state.last_error}</Alert>}
  </div>;
  const cancel = state?.stored ? () => { setValues({}); setReplacing(false); } : onCancel;
  return <>
    {fields.map((field, index) => <label key={field.name}><span className="field-label-row">{t(field.label)}{index === 0 && <GuideLink provider={provider} />}</span>
      {field.secret
        ? <PasswordInput value={values[field.name] || ""} autoComplete="new-password" onChange={(e) => setValues((v) => ({ ...v, [field.name]: e.target.value }))} />
        : <input value={values[field.name] || ""} autoComplete="off" onChange={(e) => setValues((v) => ({ ...v, [field.name]: e.target.value }))} />}
    </label>)}
    <div className="form-footer split">
      {cancel ? <button type="button" className="button ghost" disabled={busy} onClick={cancel}>{t("common.cancel")}</button> : <span />}
      <button type="button" className="button primary" disabled={busy || !complete} onClick={save}>{busy ? <LoaderCircle className="spin" size={16} /> : <Save size={16} />} {t("phone.settings.save")}</button>
    </div>
  </>;
}
