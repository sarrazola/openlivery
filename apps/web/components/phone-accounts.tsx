"use client";

import { useEffect, useState } from "react";
import { CheckCircle2, LoaderCircle, Phone, Save, Trash2 } from "lucide-react";
import { Alert } from "@/components/ui";
import { PasswordInput } from "@/components/password-input";
import { useToast } from "@/components/toast";
import { api, messageFrom } from "@/lib/api";
import { useT, type I18nKey } from "@/lib/i18n";
import type { CallAccount, CallProvider } from "@/types";

type Field = { name: "api_key" | "account_sid" | "auth_token"; label: I18nKey; secret: boolean };
const ACCOUNTS: { provider: CallProvider; title: I18nKey; copy: I18nKey; fields: Field[] }[] = [
  { provider: "elevenlabs", title: "phone.settings.elevenlabsTitle", copy: "phone.settings.elevenlabsCopy", fields: [{ name: "api_key", label: "phone.settings.apiKey", secret: true }] },
  { provider: "twilio", title: "phone.settings.twilioTitle", copy: "phone.settings.twilioCopy", fields: [
    { name: "account_sid", label: "phone.settings.accountSid", secret: false },
    { name: "auth_token", label: "phone.settings.authToken", secret: true },
  ] },
  { provider: "telnyx", title: "phone.settings.telnyxTitle", copy: "phone.settings.telnyxCopy", fields: [{ name: "api_key", label: "phone.settings.apiKey", secret: true }] },
];

/** Settings > Phone calls: the agency's ElevenLabs key and its carrier
 * accounts. Each is checked with the provider before it is stored. */
export function PhoneAccounts() {
  const t = useT();
  const [accounts, setAccounts] = useState<CallAccount[] | null>(null);
  const load = () => api<CallAccount[]>("/phone/accounts").then(setAccounts).catch(() => setAccounts([]));
  useEffect(() => { load(); }, []);

  return <section className="section-block"><div className="section-heading"><div><h2><Phone size={18} /> {t("phone.settings.heading")}</h2><p>{t("phone.settings.copy")}</p></div></div>
    {accounts && ACCOUNTS.map((preset) => (
      <AccountCard key={preset.provider} preset={preset} state={accounts.find((a) => a.provider === preset.provider)} onChange={load} />
    ))}
  </section>;
}

function AccountCard({ preset, state, onChange }: { preset: (typeof ACCOUNTS)[number]; state?: CallAccount; onChange: () => void }) {
  const t = useT();
  const toast = useToast();
  const [values, setValues] = useState<Record<string, string>>({});
  const [replacing, setReplacing] = useState(false);
  const [busy, setBusy] = useState(false);
  const stored = Boolean(state?.stored) && !replacing;
  const complete = preset.fields.every((field) => (values[field.name] || "").trim());

  async function save() {
    setBusy(true);
    try {
      const body = JSON.stringify(Object.fromEntries(preset.fields.map((f) => [f.name, (values[f.name] || "").trim()])));
      const test = await api<{ ok: boolean; message: string }>(`/phone/accounts/${preset.provider}/validate`, { method: "POST", body });
      if (!test.ok) { toast.error(test.message); return; }
      await api(`/phone/accounts/${preset.provider}`, { method: "PUT", body });
      toast.success(test.message);
      setValues({}); setReplacing(false); onChange();
    } catch (err) { toast.error(messageFrom(err)); } finally { setBusy(false); }
  }

  async function remove() {
    setBusy(true);
    try { await api(`/phone/accounts/${preset.provider}`, { method: "DELETE" }); toast.success(t("phone.settings.removed")); onChange(); }
    catch (err) { toast.error(messageFrom(err)); } finally { setBusy(false); }
  }

  return <section className="form-section"><div className="section-copy"><h2>{t(preset.title)}</h2><p>{t(preset.copy)}</p></div>
    <div className="form-fields">
      {stored ? <div className="key-configured">
        <span className="key-configured-status"><CheckCircle2 size={18} /> {t("phone.settings.connected", { hint: state?.secret_hint || "" })}</span>
        {state?.last_error && <Alert>{state.last_error}</Alert>}
        <div className="key-configured-actions">
          <button type="button" className="button ghost" disabled={busy} onClick={() => { setValues({}); setReplacing(true); }}>{t("phone.settings.replace")}</button>
          <button type="button" className="button danger" disabled={busy} onClick={remove}><Trash2 size={15} /> {t("phone.settings.remove")}</button>
        </div>
      </div> : <>
        {preset.fields.map((field) => <label key={field.name}>{t(field.label)}
          {field.secret
            ? <PasswordInput value={values[field.name] || ""} autoComplete="new-password" onChange={(e) => setValues((v) => ({ ...v, [field.name]: e.target.value }))} />
            : <input value={values[field.name] || ""} autoComplete="off" onChange={(e) => setValues((v) => ({ ...v, [field.name]: e.target.value }))} />}
        </label>)}
        <div className="form-footer split">
          {state?.stored ? <button type="button" className="button ghost" disabled={busy} onClick={() => { setValues({}); setReplacing(false); }}>{t("common.cancel")}</button> : <span />}
          <button type="button" className="button primary" disabled={busy || !complete} onClick={save}>{busy ? <LoaderCircle className="spin" size={16} /> : <Save size={16} />} {t("phone.settings.save")}</button>
        </div>
      </>}
    </div>
  </section>;
}
