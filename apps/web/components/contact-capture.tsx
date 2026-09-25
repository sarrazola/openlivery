"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { LoaderCircle } from "lucide-react";
import { Alert } from "@/components/ui";
import { AiHint } from "@/components/ai-hint";
import { api, messageFrom } from "@/lib/api";
import { useT } from "@/lib/i18n";
import type { CaptureConfig, ContactField } from "@/types";

/** The channel groups a field can be limited to. Both WhatsApp lines are one
 * choice here, so the label is plain "WhatsApp", not the inbox's per-line one. */
function channelKey(channel: string): "agents.capture.channelWhatsapp" | "agents.capture.channelInstagram" | "agents.capture.channelMessenger" | "agents.capture.channelWidget" {
  return channel === "whatsapp" ? "agents.capture.channelWhatsapp" : channel === "instagram" ? "agents.capture.channelInstagram" : channel === "messenger" ? "agents.capture.channelMessenger" : "agents.capture.channelWidget";
}

/** Which of the client's contact fields this agent asks the customer for,
 * and on which channels. What a field is and when to ask for it lives on the
 * field itself (the client's Fields tab), so every agent asks the same way.
 * The list is saved as a whole with one button, like the escalation rules. */
export function ContactCaptureEditor({ agentId, clientId }: { agentId: string; clientId: string }) {
  const t = useT();
  const [enabled, setEnabled] = useState(false);
  const [available, setAvailable] = useState<ContactField[]>([]);
  // Channel groups per picked field key; a key absent here is not asked for.
  const [picked, setPicked] = useState<Record<string, string[]>>({});
  const [channels, setChannels] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);

  const apply = (config: CaptureConfig) => {
    setEnabled(config.enabled);
    setAvailable(config.available);
    setChannels(config.channels);
    setPicked(Object.fromEntries(config.fields.map((row) => [row.field_key, row.channels])));
  };
  const load = useCallback(async () => apply(await api<CaptureConfig>(`/agents/${agentId}/capture`)), [agentId]);
  useEffect(() => {
    setLoading(true);
    load().catch((err) => setError(messageFrom(err))).finally(() => setLoading(false));
  }, [load]);

  const labelOf = (field: ContactField) =>
    field.builtin && (field.key === "name" || field.key === "email" || field.key === "phone") ? t(`agents.capture.builtin_${field.key}`) : field.label;
  const toggleField = (key: string) => setPicked((current) => {
    const next = { ...current };
    if (key in next) delete next[key]; else next[key] = [];
    return next;
  });
  const toggleChannel = (key: string, channel: string) => setPicked((current) => {
    const list = current[key] ?? [];
    return { ...current, [key]: list.includes(channel) ? list.filter((item) => item !== channel) : [...list, channel] };
  });

  async function save() {
    setBusy(true); setError(""); setSaved(false);
    try {
      const fields = available.filter((field) => field.key in picked).map((field) => ({ field_key: field.key, channels: picked[field.key] }));
      apply(await api<CaptureConfig>(`/agents/${agentId}/capture`, { method: "PUT", body: JSON.stringify({ enabled, fields }) }));
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } catch (err) { setError(messageFrom(err)); } finally { setBusy(false); }
  }

  return (
    <section className="settings-section">
      <div className="settings-copy">
        <h3>{t("agents.capture.heading")} <AiHint text={t("agents.capture.aiHint")} /></h3>
        <p>{t("agents.capture.copy")}</p>
      </div>
      <div className="settings-fields capture-editor">
        {loading ? <div className="no-conversations"><LoaderCircle className="spin" size={16} /></div> : <>
          <label className="switch-row"><span><strong>{t("agents.capture.toggle")}</strong><small>{t("agents.capture.toggleHint")}</small></span><input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} /></label>
          {enabled && <>
            <div className="capture-list">
              {available.map((field) => {
                const on = field.key in picked;
                return <div key={field.key} className={`capture-field${on ? " on" : ""}`}>
                  <label className="capture-field-head">
                    <input type="checkbox" checked={on} onChange={() => toggleField(field.key)} />
                    <span className="capture-field-text"><strong>{labelOf(field)} <span className="pill">{t(`clients.fields.kind_${field.kind}`)}</span></strong><small>{field.description || t("clients.fields.noDescription")}</small></span>
                  </label>
                  {on && <div className="capture-channels">
                    <small>{t("agents.capture.channelsLabel")}</small>
                    {channels.map((channel) => <button type="button" key={channel} className={`chip-toggle${picked[field.key].includes(channel) ? " active" : ""}`} aria-pressed={picked[field.key].includes(channel)} onClick={() => toggleChannel(field.key, channel)}>{t(channelKey(channel))}</button>)}
                    {!picked[field.key].length && <small className="muted">{t("agents.capture.allChannels")}</small>}
                  </div>}
                </div>;
              })}
            </div>
            <p className="field-help"><Link href={`/clients/${clientId}?tab=fields`} className="text-button">{t("agents.capture.manageFields")}</Link></p>
          </>}
          {error && <Alert>{error}</Alert>}
          <div className="form-footer escalation-footer">
            <span className="escalation-save">{saved && <span className="escalation-saved">{t("agents.escalation.savedNote")}</span>}<button type="button" className="button primary" onClick={save} disabled={busy}>{busy ? <LoaderCircle className="spin" size={16} /> : t("agents.capture.save")}</button></span>
          </div>
        </>}
      </div>
    </section>
  );
}
