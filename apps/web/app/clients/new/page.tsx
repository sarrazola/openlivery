"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import { ArrowLeft, ArrowRight, LoaderCircle } from "lucide-react";
import { useRouter } from "next/navigation";
import { PageHead } from "@/components/ui";
import { IndustryPicker, type IndustryValue } from "@/components/industry-picker";
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
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true);
    const data = new FormData(event.currentTarget);
    try {
      const created = await api<Client>("/clients", { method: "POST", body: JSON.stringify({ name: data.get("name"), industry: business.industry, business_type: business.businessType, business_custom: business.custom, is_active: true }) });
      router.push(`/agents/new?client=${created.id}`);
    } catch (err) { toast.error(messageFrom(err)); setBusy(false); }
  }
  return <div className="page narrow-page"><Link href="/clients" className="back-link"><ArrowLeft size={17} /> {t("clients.new.back")}</Link><PageHead eyebrow={t("clients.new.eyebrow")} title={t("clients.new.title")} description={t("clients.new.description")} />
    <form className="page-form" onSubmit={submit}><section className="form-section"><div className="section-copy"><h2>{t("clients.new.generalInfo")}</h2><p>{t("clients.new.generalInfoCopy")}</p></div><div className="form-fields"><IndustryPicker value={business} autoFocus onChange={setBusiness} /><label>{t("clients.new.name")}<input name="name" required placeholder={t("clients.new.namePlaceholder")} /></label></div></section><div className="form-footer"><Link href="/clients" className="button secondary">{t("clients.new.cancel")}</Link><button className="button primary" disabled={busy}>{busy ? <LoaderCircle className="spin" size={17} /> : <ArrowRight size={17} />} {t("clients.new.createClient")}</button></div></form>
  </div>;
}
