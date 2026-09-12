"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Bot, Building2, LoaderCircle, MessageSquareText, ShieldCheck } from "lucide-react";
import { api, messageFrom } from "@/lib/api";
import { useT } from "@/lib/i18n";
import { Alert } from "@/components/ui";
import { PasswordInput } from "@/components/password-input";

type AuthStatus = { needs_setup: boolean; registration_open: boolean };

export default function LoginPage() {
  const t = useT();
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [authStatus, setAuthStatus] = useState<AuthStatus | null>(null);
  const [statusFailed, setStatusFailed] = useState(false);
  const [statusAttempt, setStatusAttempt] = useState(0);
  const mode = authStatus?.needs_setup ? "register" : "login";

  useEffect(() => {
    let active = true;
    api<AuthStatus>("/auth/status")
      .then((status) => {
        if (active) setAuthStatus(status);
      })
      .catch(() => { if (active) setStatusFailed(true); });
    return () => { active = false; };
  }, [statusAttempt]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!authStatus || busy) return;
    setBusy(true);
    setError("");
    const data = Object.fromEntries(new FormData(event.currentTarget));
    try {
      await api(mode === "login" ? "/auth/login" : "/auth/register", { method: "POST", body: JSON.stringify(data) });
      router.push("/");
      router.refresh();
    } catch (err) {
      setError(messageFrom(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="access-page agency-access">
      <header className="access-topbar">
        <div className="access-brand"><span className="openlivery-icon"><img src="/brand/openlivery-logo-original.png" alt="" /></span><strong>OpenLivery</strong></div>
        <small>{t("auth.tagline")}</small>
      </header>
      <div className="access-layout">
        <section className="access-intro">
          <span className="access-eyebrow">{t("auth.introEyebrow")}</span>
          <h1>{t("auth.introTitle")}</h1>
          <p>{t("auth.introDescription")}</p>
          <div className="access-preview" aria-hidden="true">
            <header><div><span className="preview-logo openlivery-icon"><img src="/brand/openlivery-logo-original.png" alt="" /></span><strong>{t("auth.previewTitle")}</strong></div><small>{t("auth.previewToday")}</small></header>
            <div className="preview-metrics"><article><span>{t("auth.previewClientsActive")}</span><strong>12</strong></article><article><span>{t("auth.previewAgents")}</span><strong>28</strong></article><article><span>{t("auth.previewConversations")}</span><strong>846</strong></article></div>
            <div className="preview-list">
              <div><span className="preview-icon"><Building2 size={16} /></span><p><strong>{t("auth.previewClinicName")}</strong><small>{t("auth.previewClinicMeta")}</small></p><em>{t("auth.previewActive")}</em></div>
              <div><span className="preview-icon"><MessageSquareText size={16} /></span><p><strong>{t("auth.previewInboxTitle")}</strong><small>{t("auth.previewInboxMeta")}</small></p><em>{t("auth.previewInboxTag")}</em></div>
              <div><span className="preview-icon"><Bot size={16} /></span><p><strong>{t("auth.previewKnowledgeTitle")}</strong><small>{t("auth.previewKnowledgeMeta")}</small></p><em>{t("auth.previewReady")}</em></div>
            </div>
          </div>
        </section>
        <section className="access-form-wrap">
          <div className="access-card">
            <span className="access-card-label"><ShieldCheck size={15} /> {t("auth.cardLabel")}</span>
            <h2>{mode === "register" ? t("auth.cardTitleRegister") : t("auth.cardTitleLogin")}</h2>
            <p>{mode === "register" ? t("auth.cardSubtitleRegister") : t("auth.cardSubtitleLogin")}</p>
            {!authStatus && (statusFailed ? <>
              <Alert>{t("auth.statusError")}</Alert>
              <button className="button primary full" type="button" onClick={() => {
                setStatusFailed(false);
                setStatusAttempt((attempt) => attempt + 1);
              }}>{t("auth.retryStatus")}</button>
            </> : <p role="status"><LoaderCircle className="spin" size={17} /> {t("common.loading")}</p>)}
            {authStatus && <form onSubmit={submit} className="access-form">
              {mode === "register" && <>
                <label>{t("auth.agencyName")}<input name="agency_name" required minLength={2} placeholder={t("auth.agencyNamePlaceholder")} /></label>
                <label>{t("auth.yourName")}<input name="name" required minLength={2} placeholder={t("auth.yourNamePlaceholder")} /></label>
              </>}
              <label>{t("auth.email")}<input name="email" required type="email" placeholder={t("auth.emailPlaceholder")} /></label>
              <label>{t("auth.password")}<PasswordInput name="password" required minLength={8} placeholder={t("auth.passwordPlaceholder")} /></label>
              {error && <Alert>{error}</Alert>}
              <button className="button primary full" disabled={busy}>{busy && <LoaderCircle className="spin" size={17} />}{mode === "register" ? t("auth.submitRegister") : t("auth.submitLogin")}</button>
            </form>}
            <p className="access-security"><ShieldCheck size={14} /> {t("auth.securityNote")}</p>
          </div>
        </section>
      </div>
    </main>
  );
}
