"use client";

import { useLanguage } from "@/lib/i18n";
import { useIndustries } from "@/lib/industries";
import { AiHint } from "@/components/ai-hint";

export type IndustryValue = { industry: string; businessType: string; custom: string };

// The business is identified only when both levels are chosen, and "other"
// at either level comes with the client's own words.
export function isBusinessComplete(value: IndustryValue): boolean {
  if (!value.industry) return false;
  if (value.industry === "other") return value.custom.trim().length > 0;
  if (!value.businessType) return false;
  return value.businessType === "other" ? value.custom.trim().length > 0 : true;
}

type Props = {
  value: IndustryValue;
  onChange: (value: IndustryValue) => void;
  autoFocus?: boolean;
};

// Two dependent selects: the industry, then a business type within it. Both
// end in "other"; picking it opens a text field for the client's own words,
// which then describe the business wherever a label is needed.
export function IndustryPicker({ value, onChange, autoFocus }: Props) {
  const { t, lang } = useLanguage();
  const catalog = useIndustries();
  const sector = catalog.find((item) => item.code === value.industry);
  const industryIsOther = value.industry === "other";
  const needsWords = industryIsOther || value.businessType === "other";
  const words = <label><span className="label-row">{t("clients.industry.customLabel")} <AiHint text={t("aiContext.businessCustom")} /></span><input value={value.custom} maxLength={120} required onChange={(e) => onChange({ ...value, custom: e.target.value })} placeholder={t("clients.industry.customPlaceholder")} /></label>;
  return <>
    <div className="form-grid">
      <label><span className="label-row">{t("clients.industry.label")} <AiHint text={t("aiContext.industry")} /></span>
        <select value={value.industry} required autoFocus={autoFocus} onChange={(e) => onChange({ industry: e.target.value, businessType: e.target.value === "other" ? "other" : "", custom: "" })}>
          <option value="">{t("clients.industry.pick")}</option>
          {catalog.map((item) => <option key={item.code} value={item.code}>{item.label[lang]}</option>)}
        </select>
      </label>
      {industryIsOther ? words : <label><span className="label-row">{t("clients.industry.typeLabel")} <AiHint text={t("aiContext.businessType")} /></span>
        <select value={value.businessType} required disabled={!sector} onChange={(e) => onChange({ ...value, businessType: e.target.value, custom: "" })}>
          <option value="">{sector ? t("clients.industry.typePick") : t("clients.industry.typeFirst")}</option>
          {sector?.types.map((item) => <option key={item.code} value={item.code}>{item.label[lang]}</option>)}
        </select>
      </label>}
    </div>
    {needsWords && !industryIsOther && words}
  </>;
}
