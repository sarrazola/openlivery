"use client";

import Link from "next/link";
import { FormEvent, useEffect, useRef, useState } from "react";
import { ArrowLeft, ArrowRight, ImagePlus, LoaderCircle, Trash2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { PageHead } from "@/components/ui";
import { IndustryPicker, isBusinessComplete, type IndustryValue } from "@/components/industry-picker";
import { AiHint } from "@/components/ai-hint";
import { useToast } from "@/components/toast";
import { api, messageFrom } from "@/lib/api";
import { useT } from "@/lib/i18n";
import type { Client } from "@/types";

// The client is the identity of the business: what it is called and what
// kind of business it is. Everything about what it does lives in its agents,
// so creating one leads straight into creating the first agent.
export default function NewClientPage() {
  const t = useT();
  const toast = useToast();
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [business, setBusiness] = useState<IndustryValue>({ industry: "", businessType: "", custom: "" });
  const [name, setName] = useState("");
  const complete = isBusinessComplete(business);
  // Optional logo, uploaded right after the client exists.
  const [logo, setLogo] = useState<File | null>(null);
  const [logoUrl, setLogoUrl] = useState("");
  const logoRef = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (!logo) { setLogoUrl(""); return; }
    const url = URL.createObjectURL(logo); setLogoUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [logo]);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true);
    if (!complete || !name.trim()) { setBusy(false); return; }
    try {
      const created = await api<Client>("/clients", { method: "POST", body: JSON.stringify({ name: name.trim(), industry: business.industry, business_type: business.businessType, business_custom: business.custom, is_active: true }) });
      if (logo) {
        const data = new FormData(); data.append("file", logo);
        try { await api(`/clients/${created.id}/logo`, { method: "POST", body: data }); }
        catch (err) { toast.error(messageFrom(err)); }
      }
      router.push(`/agents/new?client=${created.id}`);
    } catch (err) { toast.error(messageFrom(err)); setBusy(false); }
  }
  return <div className="page narrow-page"><Link href="/clients" className="back-link"><ArrowLeft size={17} /> {t("clients.new.back")}</Link><PageHead eyebrow={t("clients.new.eyebrow")} title={t("clients.new.title")} description={t("clients.new.description")} />
    <form className="page-form" onSubmit={submit}><section className="form-section"><div className="section-copy"><h2>{t("clients.new.generalInfo")}</h2><p>{t("clients.new.generalInfoCopy")}</p></div><div className="form-fields"><IndustryPicker value={business} autoFocus onChange={setBusiness} /><label><span className="label-row">{t("clients.new.name")} <AiHint text={t("aiContext.businessName")} /></span><input name="name" required value={name} disabled={!complete} onChange={(e) => setName(e.target.value)} placeholder={complete ? t("clients.new.namePlaceholder") : t("clients.new.nameLocked")} /></label><div className="logo-editor"><div className="logo-pick"><button type="button" className="text-button" onClick={() => logoRef.current?.click()}>{logo ? t("clients.detail.logoChange") : t("clients.new.logoAdd")}</button><button type="button" className="logo-preview" onClick={() => logoRef.current?.click()}>{logoUrl ? <img src={logoUrl} alt={t("clients.detail.logoAlt")} /> : <ImagePlus size={24} />}</button></div><div><strong>{t("clients.detail.logoLabel")}</strong><small>{t("clients.new.logoHint")}</small>{logo && <div><button type="button" className="text-button danger-text" onClick={() => setLogo(null)}><Trash2 size={14} /> {t("clients.detail.logoRemove")}</button></div>}</div><input ref={logoRef} hidden type="file" accept="image/png,image/jpeg,image/webp,image/svg+xml" onChange={(e) => setLogo(e.target.files?.[0] ?? null)} /></div></div></section><div className="form-footer"><Link href="/clients" className="button secondary">{t("clients.new.cancel")}</Link><button className="button primary" disabled={busy || !complete || !name.trim()}>{busy ? <LoaderCircle className="spin" size={17} /> : <ArrowRight size={17} />} {t("clients.new.createClient")}</button></div></form>
  </div>;
}
