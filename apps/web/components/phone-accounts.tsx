"use client";

import { useEffect, useState } from "react";
import { CheckCircle2, LoaderCircle, Phone, Plus, Save, Trash2 } from "lucide-react";
import { Alert } from "@/components/ui";
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
    { name: "account_sid", label: "phone.settings.accountSid", secret: false },
    { name: "auth_token", label: "phone.settings.authToken", secret: true },
  ],
  telnyx: [{ name: "api_key", label: "phone.settings.apiKey", secret: true }],
};
const CARRIERS: { id: Carrier; name: string; hint: I18nKey }[] = [
  { id: "twilio", name: "Twilio", hint: "phone.settings.twilioCopy" },
  { id: "telnyx", name: "Telnyx", hint: "phone.settings.telnyxCopy" },
];
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
        <div className="form-fields"><AccountForm provider="elevenlabs" state={stateOf("elevenlabs")} onChange={load} /></div>
      </section>
      <CarrierSection stateOf={stateOf} onChange={load} />
    </>}
  </section>;
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
  const picked = CARRIERS.find((c) => c.id === carrier) ?? CARRIERS[0];

  return <section className="form-section"><div className="section-copy"><h2>{t("phone.settings.carrierTitle")}</h2><p>{t("phone.settings.carrierCopy")}</p></div>
    <div className="form-fields">
      {connected.map((c) => <div key={c.id} className="carrier-connected"><strong>{c.name}</strong><AccountForm provider={c.id} state={stateOf(c.id)} onChange={onChange} /></div>)}
      {showForm && <>
        <div className="segmented" role="radiogroup" aria-label={t("phone.settings.carrierLabel")}>
          {(adding ? available : CARRIERS).map((c) => <button key={c.id} type="button" role="radio" aria-checked={carrier === c.id} className={carrier === c.id ? "active" : ""} onClick={() => setCarrier(c.id)}>{c.name}</button>)}
        </div>
        <p className="field-help">{t(picked.hint)}</p>
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

  async function remove() {
    setBusy(true);
    try { await api(`/phone/accounts/${provider}`, { method: "DELETE" }); toast.success(t("phone.settings.removed")); onChange(); }
    catch (err) { toast.error(messageFrom(err)); } finally { setBusy(false); }
  }

  if (stored) return <div className="key-configured">
    <span className="key-configured-status"><CheckCircle2 size={18} /> {t("phone.settings.connected", { name: nameOf(provider), hint: state?.secret_hint || "" })}</span>
    {state?.last_error && <Alert>{state.last_error}</Alert>}
    <div className="key-configured-actions">
      <button type="button" className="button ghost" disabled={busy} onClick={() => { setValues({}); setReplacing(true); }}>{t("phone.settings.replace")}</button>
      <button type="button" className="button danger" disabled={busy} onClick={remove}><Trash2 size={15} /> {t("phone.settings.remove")}</button>
    </div>
  </div>;
  const cancel = state?.stored ? () => { setValues({}); setReplacing(false); } : onCancel;
  return <>
    {fields.map((field) => <label key={field.name}>{t(field.label)}
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
