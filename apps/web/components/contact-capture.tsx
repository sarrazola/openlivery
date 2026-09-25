"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { ArrowDown, ArrowUp, LoaderCircle, Plus, RotateCcw, Trash2 } from "lucide-react";
import { Alert } from "@/components/ui";
import { AiHint } from "@/components/ai-hint";
import { api, messageFrom } from "@/lib/api";
import { useT } from "@/lib/i18n";
import type { CaptureConfig, CaptureField, ContactField, ContactFieldKind } from "@/types";

const KINDS: ContactFieldKind[] = ["text", "number", "email", "phone"];
const NEW_FIELD = "__new__";

/** The channel groups a field can be limited to. Both WhatsApp lines are one
 * choice here, so the label is plain "WhatsApp", not the inbox's per-line one. */
function channelKey(channel: string): "agents.capture.channelWhatsapp" | "agents.capture.channelInstagram" | "agents.capture.channelMessenger" | "agents.capture.channelWidget" {
  return channel === "whatsapp" ? "agents.capture.channelWhatsapp" : channel === "instagram" ? "agents.capture.channelInstagram" : channel === "messenger" ? "agents.capture.channelMessenger" : "agents.capture.channelWidget";
}

/** What the agent asks the customer for and saves on the contact: the
 * built-in name, email and phone, or any field the client defined. Each
 * entry carries the operator's instruction (when and how to ask) and the
 * channels it applies to; the list is edited as a whole and saved with one
 * button, like the escalation rules. */
export function ContactCaptureEditor({ agentId, clientId }: { agentId: string; clientId: string }) {
  const t = useT();
  const [enabled, setEnabled] = useState(false);
  const [fields, setFields] = useState<CaptureField[]>([]);
  const [available, setAvailable] = useState<ContactField[]>([]);
  const [channels, setChannels] = useState<string[]>([]);
  const [picking, setPicking] = useState("");
  const [creating, setCreating] = useState(false);
  const [draft, setDraft] = useState({ key: "", label: "", kind: "text" as ContactFieldKind, description: "" });
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);

  const load = useCallback(async () => {
    const config = await api<CaptureConfig>(`/agents/${agentId}/capture`);
    setEnabled(config.enabled);
    setFields(config.fields);
    setAvailable(config.available);
    setChannels(config.channels);
  }, [agentId]);
  useEffect(() => {
    setLoading(true);
    load().catch((err) => setError(messageFrom(err))).finally(() => setLoading(false));
  }, [load]);

  const unused = available.filter((field) => !fields.some((row) => row.field_key === field.key));
  const kindLabel = (kind: ContactFieldKind) => t(`clients.fields.kind_${kind}`);
  const labelOf = (field: { key: string; label: string; builtin: boolean }) =>
    field.builtin && (field.key === "name" || field.key === "email" || field.key === "phone") ? t(`agents.capture.builtin_${field.key}`) : field.label;
  const patch = (index: number, changes: Partial<CaptureField>) => setFields((list) => list.map((row, i) => (i === index ? { ...row, ...changes } : row)));
  const move = (index: number, delta: number) => setFields((list) => {
    const next = [...list];
    const target = index + delta;
    if (target < 0 || target >= next.length) return list;
    [next[index], next[target]] = [next[target], next[index]];
    return next;
  });
  const addField = (field: ContactField, instruction = "") => setFields((list) => [...list, { field_key: field.key, label: field.label, kind: field.kind, builtin: field.builtin, instruction, channels: [] }]);
  const toggleChannel = (index: number, channel: string) => {
    const row = fields[index];
    const next = row.channels.includes(channel) ? row.channels.filter((item) => item !== channel) : [...row.channels, channel];
    patch(index, { channels: next });
  };

  /** Name and email, asked the way the screenshot in the request does. */
  function restoreDefault() {
    const name = available.find((field) => field.key === "name");
    const email = available.find((field) => field.key === "email");
    setFields([
      ...(name ? [{ field_key: name.key, label: labelOf(name), kind: name.kind, builtin: true, instruction: t("agents.capture.defaultNameInstruction"), channels: [] }] : []),
      ...(email ? [{ field_key: email.key, label: labelOf(email), kind: email.kind, builtin: true, instruction: t("agents.capture.defaultEmailInstruction"), channels: [] }] : []),
    ]);
    setEnabled(true);
  }

  function pick(value: string) {
    setPicking("");
    if (value === NEW_FIELD) { setCreating(true); return; }
    const field = available.find((item) => item.key === value);
    if (field) addField(field);
  }

  async function createField() {
    const key = draft.key.trim();
    const label = draft.label.trim();
    if (!key || !label) return;
    setBusy(true); setError("");
    try {
      const created = await api<ContactField>(`/clients/${clientId}/contact-fields`, {
        method: "POST", body: JSON.stringify({ key, label, kind: draft.kind, description: draft.description.trim() }),
      });
      setAvailable((list) => [...list, created]);
      addField(created);
      setCreating(false);
      setDraft({ key: "", label: "", kind: "text", description: "" });
    } catch (err) { setError(messageFrom(err)); } finally { setBusy(false); }
  }

  async function save() {
    setBusy(true); setError(""); setSaved(false);
    try {
      const payload = { enabled, fields: fields.map((row) => ({ field_key: row.field_key, instruction: row.instruction.trim(), channels: row.channels })) };
      const config = await api<CaptureConfig>(`/agents/${agentId}/capture`, { method: "PUT", body: JSON.stringify(payload) });
      setEnabled(config.enabled); setFields(config.fields); setAvailable(config.available);
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
            {fields.map((row, index) => <div key={row.field_key} className="capture-field">
              <div className="capture-field-head">
                <div><strong>{labelOf({ key: row.field_key, label: row.label, builtin: row.builtin })}</strong> <code>{row.field_key}</code> <span className="pill">{kindLabel(row.kind)}</span></div>
                <span className="escalation-actions">
                  <button type="button" className="icon-button" onClick={() => move(index, -1)} disabled={index === 0} title={t("agents.escalation.moveUp")} aria-label={t("agents.escalation.moveUp")}><ArrowUp size={14} /></button>
                  <button type="button" className="icon-button" onClick={() => move(index, 1)} disabled={index === fields.length - 1} title={t("agents.escalation.moveDown")} aria-label={t("agents.escalation.moveDown")}><ArrowDown size={14} /></button>
                  <button type="button" className="icon-button danger" onClick={() => setFields((list) => list.filter((_, i) => i !== index))} title={t("agents.capture.remove")} aria-label={t("agents.capture.remove")}><Trash2 size={14} /></button>
                </span>
              </div>
              <textarea rows={2} value={row.instruction} maxLength={1000} onChange={(e) => patch(index, { instruction: e.target.value })} placeholder={t("agents.capture.instructionPlaceholder")} aria-label={t("agents.capture.instructionLabel")} />
              <div className="capture-channels">
                <small>{t("agents.capture.channelsLabel")}</small>
                {channels.map((channel) => <button type="button" key={channel} className={`chip-toggle${row.channels.includes(channel) ? " active" : ""}`} aria-pressed={row.channels.includes(channel)} onClick={() => toggleChannel(index, channel)}>{t(channelKey(channel))}</button>)}
                {!row.channels.length && <small className="muted">{t("agents.capture.allChannels")}</small>}
              </div>
            </div>)}
            {!fields.length && <p className="esc-empty">{t("agents.capture.empty")}</p>}
            {creating ? <div className="capture-new">
              <div className="form-grid">
                <label>{t("clients.fields.labelLabel")}<input value={draft.label} maxLength={80} onChange={(e) => setDraft((d) => ({ ...d, label: e.target.value, key: d.key || e.target.value.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "").slice(0, 60) }))} placeholder={t("clients.fields.labelPlaceholder")} autoFocus /></label>
                <label>{t("clients.fields.keyLabel")}<input value={draft.key} maxLength={60} pattern="^[a-z][a-z0-9_]{1,59}$" onChange={(e) => setDraft((d) => ({ ...d, key: e.target.value }))} placeholder={t("clients.fields.keyPlaceholder")} /><span className="field-help">{t("clients.fields.keyHelp")}</span></label>
              </div>
              <div className="form-grid">
                <label>{t("clients.fields.kindLabel")}<select value={draft.kind} onChange={(e) => setDraft((d) => ({ ...d, kind: e.target.value as ContactFieldKind }))}>{KINDS.map((kind) => <option key={kind} value={kind}>{kindLabel(kind)}</option>)}</select></label>
                <label>{t("clients.fields.descriptionLabel")}<input value={draft.description} maxLength={1000} onChange={(e) => setDraft((d) => ({ ...d, description: e.target.value }))} placeholder={t("clients.fields.descriptionPlaceholder")} /></label>
              </div>
              <div className="capture-new-actions">
                <button type="button" className="button small" onClick={() => setCreating(false)}>{t("common.cancel")}</button>
                <button type="button" className="button primary small" disabled={busy || !draft.key.trim() || !draft.label.trim() || !/^[a-z][a-z0-9_]{1,59}$/.test(draft.key.trim())} onClick={createField}>{busy ? <LoaderCircle className="spin" size={14} /> : <Plus size={14} />} {t("clients.fields.create")}</button>
              </div>
            </div> : <div className="esc-rules-foot capture-foot">
              <select value={picking} onChange={(e) => pick(e.target.value)} aria-label={t("agents.capture.addField")}>
                <option value="">{t("agents.capture.addField")}</option>
                {unused.map((field) => <option key={field.key} value={field.key}>{labelOf(field)} ({field.key})</option>)}
                <option value={NEW_FIELD}>{t("agents.capture.newField")}</option>
              </select>
              <button type="button" className="text-button" onClick={restoreDefault}><RotateCcw size={14} /> {t("agents.capture.restoreDefault")}</button>
              <Link href={`/clients/${clientId}?tab=fields`} className="text-button">{t("agents.capture.manageFields")}</Link>
            </div>}
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
