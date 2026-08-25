"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { CheckCircle2, Eye, EyeOff, ImagePlus, LoaderCircle, Save, ShieldCheck, Trash2 } from "lucide-react";
import { PageHead } from "@/components/ui";
import { FormSkeleton } from "@/components/skeleton";
import { useToast } from "@/components/toast";
import { api, messageFrom } from "@/lib/api";
import { useT, type TranslateFn } from "@/lib/i18n";
import { PROVIDERS } from "@/lib/providers";
import type { Agency, Provider, ProviderTest } from "@/types";

export default function SettingsPage() {
  const t = useT();
  const toast = useToast();
  const [agency, setAgency] = useState<Agency | null>(null);
  const [providers, setProviders] = useState<Provider[]>([]);
  const [busy, setBusy] = useState(false);
  const [logoVersion, setLogoVersion] = useState(0);
  const fileRef = useRef<HTMLInputElement>(null);

  const load = async () => {
    const [a, p] = await Promise.all([api<Agency>("/agency"), api<Provider[]>("/providers")]);
    setAgency(a); setProviders(p);
  };
  useEffect(() => { load(); }, []);

  async function saveIdentity(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true);
    const data = new FormData(event.currentTarget);
    try {
      setAgency(await api<Agency>("/agency", { method: "PATCH", body: JSON.stringify({ name: data.get("name"), slug: data.get("slug"), brand_color: data.get("brand_color") }) }));
      toast.success(t("settings.index.agencySaved"));
    } catch (err) { toast.error(messageFrom(err)); } finally { setBusy(false); }
  }
  async function uploadLogo(file?: File) {
    if (!file) return;
    setBusy(true); const data = new FormData(); data.append("file", file);
    try { setAgency(await api<Agency>("/agency/logo", { method: "POST", body: data })); setLogoVersion((v) => v + 1); toast.success(t("settings.index.logoUpdated")); }
    catch (err) { toast.error(messageFrom(err)); } finally { setBusy(false); if (fileRef.current) fileRef.current.value = ""; }
  }
  async function deleteLogo() { await api("/agency/logo", { method: "DELETE" }); setLogoVersion((v) => v + 1); await load(); }

  async function saveKey(provider: string, apiKey: string): Promise<boolean> {
    if (!apiKey.trim()) return false;
    setBusy(true);
    try {
      // Validate the connection before storing; on failure nothing is saved.
      const test = await api<ProviderTest>(`/providers/${provider}/validate`, { method: "POST", body: JSON.stringify({ api_key: apiKey }) });
      await api(`/providers/${provider}`, { method: "PUT", body: JSON.stringify({ api_key: apiKey }) });
      toast.success(test.message);
      await load();
      return true;
    } catch (err) { toast.error(messageFrom(err)); return false; }
    finally { setBusy(false); }
  }
  async function removeKey(provider: string) { await api(`/providers/${provider}`, { method: "DELETE" }); await load(); }

  if (!agency) return <div className="page"><PageHead eyebrow={t("settings.index.eyebrow")} title={t("settings.index.title")} description={t("settings.index.description")} /><FormSkeleton sections={2} /></div>;
  return <div className="page"><PageHead eyebrow={t("settings.index.eyebrow")} title={t("settings.index.title")} description={t("settings.index.description")} />

    <form className="page-form" onSubmit={saveIdentity}><section className="form-section"><div className="section-copy"><h2>{t("settings.index.identityHeading")}</h2><p>{t("settings.index.identityCopy")}</p></div><div className="form-fields"><div className="logo-editor"><button type="button" className="logo-preview" onClick={() => fileRef.current?.click()}>{agency.logo_url ? <img src={`${agency.logo_url}?v=${logoVersion}`} alt={t("settings.index.logoAlt")} /> : <ImagePlus size={24} />}</button><div><strong>{t("settings.index.logoLabel")}</strong><small>{t("settings.index.logoHint")}</small><div><button type="button" className="text-button" onClick={() => fileRef.current?.click()}>{t("settings.index.change")}</button>{agency.logo_url && <button type="button" className="text-button danger-text" onClick={deleteLogo}><Trash2 size={14} /> {t("settings.index.remove")}</button>}</div></div><input ref={fileRef} hidden type="file" accept="image/png,image/jpeg,image/webp,image/svg+xml" onChange={(e) => uploadLogo(e.target.files?.[0])} /></div><div className="form-grid"><label>{t("settings.index.agencyName")}<input name="name" required defaultValue={agency.name} /></label><label>{t("settings.index.identifier")}<input name="slug" required defaultValue={agency.slug} /></label></div><label>{t("settings.index.brandColor")}<div className="color-input"><input type="color" name="brand_color" defaultValue={agency.brand_color} /><input defaultValue={agency.brand_color} readOnly /></div></label><button className="button primary align-start" disabled={busy}>{busy ? <LoaderCircle size={17} className="spin" /> : <Save size={17} />} {t("settings.index.saveIdentity")}</button></div></section></form>

    <section className="section-block"><div className="section-heading"><div><h2>{t("settings.providers.heading")}</h2><p>{t("settings.providers.copy")}</p></div></div>
      <div className="security-note"><ShieldCheck size={20} /><span><strong>{t("settings.index.privateCredentials")}</strong> {t("settings.index.privateCredentialsCopy")}</span></div>
      {PROVIDERS.map((preset) => (
        <ProviderKeyCard key={preset.id} preset={preset} state={providers.find((x) => x.provider === preset.id)} busy={busy} onSave={saveKey} onRemove={removeKey} t={t} />
      ))}
    </section>
  </div>;
}

function ProviderKeyCard({ preset, state, busy, onSave, onRemove, t }: { preset: (typeof PROVIDERS)[number]; state?: Provider; busy: boolean; onSave: (p: string, k: string) => Promise<boolean>; onRemove: (p: string) => Promise<void>; t: TranslateFn }) {
  const [key, setKey] = useState("");
  const [reveal, setReveal] = useState(false);
  const [replacing, setReplacing] = useState(false);
  const configured = Boolean(state?.configured) && !replacing;

  async function save() {
    if (await onSave(preset.id, key)) { setKey(""); setReplacing(false); }
  }

  return (
    <section className="form-section"><div className="section-copy"><h2>{preset.label}</h2><p>{t("settings.providers.byo", { label: preset.label })}</p></div>
      <div className="form-fields">
        {configured ? (
          <div className="key-configured">
            <span className="key-configured-status"><CheckCircle2 size={18} /> {t("settings.providers.configured", { label: preset.label })}</span>
            <div className="key-configured-actions">
              <button type="button" className="button ghost" disabled={busy} onClick={() => { setKey(""); setReplacing(true); }}>{t("settings.providers.replace")}</button>
              <button type="button" className="button danger" disabled={busy} onClick={() => onRemove(preset.id)}><Trash2 size={15} /> {t("settings.providers.remove")}</button>
            </div>
          </div>
        ) : (
          <>
            <label>{t("settings.providers.apiKey", { label: preset.label })}
              <div className="key-input">
                <input type={reveal ? "text" : "password"} value={key} autoComplete="new-password" onChange={(e) => setKey(e.target.value)} placeholder={preset.keyPlaceholder} />
                <button type="button" className="reveal" onClick={() => setReveal((v) => !v)} aria-label={t(reveal ? "settings.providers.hide" : "settings.providers.reveal")}>{reveal ? <EyeOff size={16} /> : <Eye size={16} />}</button>
              </div>
            </label>
            <div className="form-footer split">
              {state?.configured ? <button type="button" className="button ghost" disabled={busy} onClick={() => { setKey(""); setReplacing(false); }}>{t("common.cancel")}</button> : <span />}
              <button type="button" className="button primary" disabled={busy || !key.trim()} onClick={save}>{busy ? <LoaderCircle className="spin" size={16} /> : <Save size={16} />} {t("settings.providers.save")}</button>
            </div>
          </>
        )}
      </div>
    </section>
  );
}
