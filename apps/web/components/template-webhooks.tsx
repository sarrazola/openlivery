"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { Check, ChevronDown, ChevronRight, Copy, KeyRound, LoaderCircle, Pencil, Plus, Power, Trash2 } from "lucide-react";
import { Alert, Modal } from "@/components/ui";
import { ConfirmModal } from "@/components/confirm-modal";
import { api, messageFrom } from "@/lib/api";
import { formatWhen } from "@/lib/datetime";
import { useLanguage, useT } from "@/lib/i18n";
import type { Template, TemplateWebhook, WhatsAppCloudChannel } from "@/types";

type AgentName = { id: string; name: string };

const channelName = (channel: WhatsAppCloudChannel) => channel.label || channel.display_name || channel.phone_number || channel.phone_number_id;
const templateKey = (template: { name: string; language: string }) => `${template.name}|${template.language}`;

/** What the caller posts, with a sample value in every slot the template has. */
function exampleBody(template: Template | undefined): string {
  const body: Record<string, unknown> = { phone: "573001112233" };
  if (template) {
    if (template.parameters.length) body.variables = Object.fromEntries(template.parameters.map((name) => [name, "…"]));
    const header = template.header;
    if (header && (header.parameters.length || ["IMAGE", "VIDEO", "DOCUMENT"].includes(header.format))) body.header = header.format === "TEXT" ? "…" : "https://…";
    if (header?.format === "LOCATION") body.location = { latitude: 4.438, longitude: -75.232, name: "…", address: "…" };
    if (template.buttons.some((button) => button.dynamic)) body.buttons = template.buttons.map((button) => (button.dynamic ? "…" : ""));
  }
  body.context = "…";
  return JSON.stringify(body, null, 2);
}

function CopyButton({ text }: { text: string }) {
  const t = useT();
  const [copied, setCopied] = useState(false);
  return <button type="button" onClick={() => { navigator.clipboard.writeText(text); setCopied(true); window.setTimeout(() => setCopied(false), 1500); }}>
    {copied ? <Check size={15} /> : <Copy size={15} />} {copied ? t("clients.webhooks.copied") : t("clients.webhooks.copy")}
  </button>;
}

/** The client's template webhooks: an address another system calls so an
 * approved WhatsApp template goes out on one number, stored as the agent's
 * message. The caller needs the address and the secret, which is shown once
 * when it is made. `base` is the client's URL, `agents` names who answers each number. */
export function TemplateWebhooksView({ base, agents }: { base: string; agents: AgentName[] }) {
  const t = useT();
  const { lang } = useLanguage();
  const [webhooks, setWebhooks] = useState<TemplateWebhook[]>([]);
  const [channels, setChannels] = useState<WhatsAppCloudChannel[] | null>(null);
  const [templates, setTemplates] = useState<Record<string, Template[]>>({});
  const [editing, setEditing] = useState<TemplateWebhook | null | "new">(null);
  const [deleting, setDeleting] = useState<TemplateWebhook | null>(null);
  const [error, setError] = useState("");
  // The list stays compact: one webhook shows its address and example at a time.
  const [open, setOpen] = useState<string | null>(null);
  // A secret is shown once, in the answer that made it; it lives here until the page is left.
  const [secrets, setSecrets] = useState<Record<string, string>>({});
  const [regenerating, setRegenerating] = useState<TemplateWebhook | null>(null);
  const clientId = base.split("/").pop();
  const [origin, setOrigin] = useState("");
  useEffect(() => { setOrigin(window.location.origin); }, []);

  const load = useCallback(async () => {
    try {
      const [rows, numbers] = await Promise.all([
        api<TemplateWebhook[]>(`${base}/webhooks`),
        api<WhatsAppCloudChannel[]>(`/whatsapp-cloud/clients/${clientId}/channels`),
      ]);
      setWebhooks(rows); setChannels(numbers);
    } catch (err) { setError(messageFrom(err)); }
  }, [base, clientId]);
  useEffect(() => { load(); }, [load]);

  const loadTemplates = useCallback(async (channelId: string) => {
    if (!channelId) return;
    try {
      const rows = await api<Template[]>(`${base}/webhooks/templates?channel_id=${channelId}`);
      setTemplates((current) => ({ ...current, [channelId]: rows }));
    } catch (err) { setTemplates((current) => ({ ...current, [channelId]: [] })); setError(messageFrom(err)); }
  }, [base]);
  // Each row shows its example call, which needs the template's variables.
  useEffect(() => {
    Array.from(new Set(webhooks.map((webhook) => webhook.channel_id))).forEach((channelId) => { if (!(channelId in templates)) loadTemplates(channelId); });
  }, [webhooks, templates, loadTemplates]);

  async function toggle(webhook: TemplateWebhook) {
    try {
      await api(`${base}/webhooks/${webhook.id}`, { method: "PATCH", body: JSON.stringify({ is_enabled: !webhook.is_enabled }) });
      await load();
    } catch (err) { setError(messageFrom(err)); }
  }

  async function regenerate(webhook: TemplateWebhook) {
    const fresh = await api<TemplateWebhook>(`${base}/webhooks/${webhook.id}/secret`, { method: "POST" });
    if (fresh.secret) setSecrets((current) => ({ ...current, [webhook.id]: fresh.secret as string }));
    setRegenerating(null); setOpen(webhook.id);
    await load();
  }

  async function remove(webhook: TemplateWebhook) {
    await api(`${base}/webhooks/${webhook.id}`, { method: "DELETE" });
    setDeleting(null);
    await load();
  }

  return <section className="form-section">
    <div className="section-copy"><h2>{t("clients.webhooks.title")}</h2><p>{t("clients.webhooks.intro")}</p></div>
    <div className="form-fields contact-fields">
      {channels !== null && !channels.length && <p className="esc-empty">{t("clients.webhooks.noChannel")}</p>}
      {webhooks.map((webhook) => {
        // The address people reach this app at, which is where a caller reaches it too.
        const url = `${origin}/api/public/hooks/${webhook.id}`;
        const secret = secrets[webhook.id];
        const known = templates[webhook.channel_id];
        const template = known?.find((item) => templateKey(item) === `${webhook.template_name}|${webhook.template_language}`);
        const example = `curl -X POST ${url} \\\n  -H "Authorization: Bearer ${secret ?? t("clients.webhooks.secretPlaceholder")}" \\\n  -H "Content-Type: application/json" \\\n  -d '${exampleBody(template)}'`;
        const expanded = open === webhook.id;
        return <div key={webhook.id} className="contact-field-row webhook-row">
          <div className="contact-field-main">
            <button type="button" className="webhook-toggle" onClick={() => setOpen(expanded ? null : webhook.id)} aria-expanded={expanded} title={expanded ? t("clients.webhooks.hideDetails") : t("clients.webhooks.showDetails")}>
              {expanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
              <span className="contact-field-text">
                <strong>{webhook.name} {!webhook.is_enabled && <span className="pill">{t("clients.webhooks.off")}</span>}</strong>
                <small>{t("clients.webhooks.sends", { template: webhook.template_name, language: webhook.template_language, channel: webhook.channel_label })} · {webhook.last_used_at ? t("clients.webhooks.lastUsed", { when: formatWhen(webhook.last_used_at, lang) }) : t("clients.webhooks.neverUsed")}</small>
              </span>
            </button>
            <span className="escalation-actions">
              <button type="button" className="icon-button" onClick={() => toggle(webhook)} title={webhook.is_enabled ? t("clients.webhooks.turnOff") : t("clients.webhooks.turnOn")} aria-label={webhook.is_enabled ? t("clients.webhooks.turnOff") : t("clients.webhooks.turnOn")}><Power size={15} /></button>
              <button type="button" className="icon-button" onClick={() => setEditing(webhook)} title={t("clients.webhooks.edit")} aria-label={t("clients.webhooks.edit")}><Pencil size={15} /></button>
              <button type="button" className="icon-button danger" onClick={() => setDeleting(webhook)} title={t("clients.webhooks.deleteAction")} aria-label={t("clients.webhooks.deleteAction")}><Trash2 size={15} /></button>
            </span>
          </div>
          {known && !template && <Alert>{t("clients.webhooks.templateMissing")}</Alert>}
          {expanded && <>
            <div className="webhook-detail">{t("clients.webhooks.urlLabel")}<div className="url-preview"><code>{url}</code><CopyButton text={url} /></div></div>
            <div className="webhook-detail">{t("clients.webhooks.secretLabel")}
              {secret
                ? <><div className="url-preview"><code>{secret}</code><CopyButton text={secret} /></div><span className="field-help webhook-secret-once">{t("clients.webhooks.secretOnce")}</span></>
                : <><div className="url-preview"><code>{t("clients.webhooks.secretHidden", { hint: webhook.secret_hint })}</code><button type="button" onClick={() => setRegenerating(webhook)}><KeyRound size={15} /> {t("clients.webhooks.regenerate")}</button></div><span className="field-help">{t("clients.webhooks.secretHelp")}</span></>}
            </div>
            <div className="webhook-detail">{t("clients.webhooks.exampleLabel")}<div className="url-preview webhook-example"><pre>{example}</pre><CopyButton text={example} /></div><span className="field-help">{t("clients.webhooks.exampleHelp")}</span></div>
          </>}
        </div>;
      })}
      {channels !== null && channels.length > 0 && !webhooks.length && <p className="esc-empty">{t("clients.webhooks.empty")}</p>}
      {channels !== null && channels.length > 0 && <div><button type="button" className="button secondary small" onClick={() => setEditing("new")}><Plus size={14} /> {t("clients.webhooks.newWebhook")}</button></div>}
      {error && <Alert>{error}</Alert>}
    </div>
    {editing !== null && channels && <WebhookModal
      base={base} webhook={editing === "new" ? null : editing} channels={channels} agents={agents}
      templates={templates} loadTemplates={loadTemplates}
      onClose={() => setEditing(null)} onSaved={(saved) => { setEditing(null); setOpen(saved.id); if (saved.secret) setSecrets((current) => ({ ...current, [saved.id]: saved.secret as string })); load(); }}
    />}
    {regenerating && <ConfirmModal
      title={t("clients.webhooks.regenerateTitle", { name: regenerating.name })}
      message={t("clients.webhooks.regenerateMessage")}
      confirmLabel={t("clients.webhooks.regenerate")}
      cancelLabel={t("common.cancel")}
      confirmIcon={<KeyRound size={15} />}
      onConfirm={() => regenerate(regenerating)}
      onClose={() => setRegenerating(null)}
    />}
    {deleting && <ConfirmModal
      title={t("clients.webhooks.deleteTitle", { name: deleting.name })}
      message={t("clients.webhooks.deleteMessage")}
      confirmLabel={t("clients.webhooks.deleteAction")}
      cancelLabel={t("common.cancel")}
      confirmIcon={<Trash2 size={15} />}
      onConfirm={() => remove(deleting)}
      onClose={() => setDeleting(null)}
    />}
  </section>;
}

function WebhookModal({ base, webhook, channels, agents, templates, loadTemplates, onClose, onSaved }: {
  base: string; webhook: TemplateWebhook | null; channels: WhatsAppCloudChannel[]; agents: AgentName[];
  templates: Record<string, Template[]>; loadTemplates: (channelId: string) => void; onClose: () => void; onSaved: (saved: TemplateWebhook) => void;
}) {
  const t = useT();
  const [name, setName] = useState(webhook?.name ?? "");
  const [channelId, setChannelId] = useState(webhook?.channel_id ?? channels[0]?.id ?? "");
  const [picked, setPicked] = useState(webhook ? templateKey({ name: webhook.template_name, language: webhook.template_language }) : "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const options = templates[channelId];
  useEffect(() => { if (channelId && !(channelId in templates)) loadTemplates(channelId); }, [channelId, templates, loadTemplates]);
  const template = useMemo(() => options?.find((item) => templateKey(item) === picked), [options, picked]);
  const channel = channels.find((item) => item.id === channelId);
  const agent = agents.find((item) => item.id === channel?.agent_id)?.name;
  // Every value the call has to carry, so the person wiring it sees them before saving.
  const slots = template ? [
    ...template.parameters,
    ...(template.header && (template.header.parameters.length || ["IMAGE", "VIDEO", "DOCUMENT", "LOCATION"].includes(template.header.format)) ? [t("clients.webhooks.headerVariable")] : []),
    ...(template.buttons.some((button) => button.dynamic) ? [t("clients.webhooks.buttonsVariable")] : []),
  ] : [];
  const ready = Boolean(name.trim() && channelId && template);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!ready || !template) return;
    setBusy(true); setError("");
    const body = JSON.stringify({ name: name.trim(), channel_id: channelId, template_name: template.name, template_language: template.language });
    try {
      onSaved(webhook
        ? await api<TemplateWebhook>(`${base}/webhooks/${webhook.id}`, { method: "PATCH", body })
        : await api<TemplateWebhook>(`${base}/webhooks`, { method: "POST", body }));
    } catch (err) { setError(messageFrom(err)); } finally { setBusy(false); }
  }

  return <Modal open title={webhook ? t("clients.webhooks.editTitle") : t("clients.webhooks.newTitle")} description={t("clients.webhooks.modalCopy")} onClose={onClose}>
    <form className="modal-form" onSubmit={submit}>
      <label>{t("clients.webhooks.nameLabel")}<input value={name} maxLength={120} onChange={(e) => setName(e.target.value)} placeholder={t("clients.webhooks.namePlaceholder")} autoFocus required /></label>
      <label>{t("clients.webhooks.channelLabel")}<select value={channelId} onChange={(e) => { setChannelId(e.target.value); setPicked(""); }}>{channels.map((item) => <option key={item.id} value={item.id}>{channelName(item)}</option>)}</select>
        {agent && <span className="field-help">{t("clients.webhooks.agentAnswers", { agent })}</span>}
      </label>
      <label>{t("clients.webhooks.templateLabel")}<select value={picked} onChange={(e) => setPicked(e.target.value)} disabled={!options?.length}>
        <option value="">{options ? t("clients.webhooks.templatePick") : t("clients.webhooks.templatesLoading")}</option>
        {options?.map((item) => <option key={templateKey(item)} value={templateKey(item)}>{item.name} ({item.language})</option>)}
      </select>
        <span className="field-help">{options && !options.length ? t("clients.webhooks.templatesEmpty") : t("clients.webhooks.utilityOnly")}</span>
      </label>
      {template && <div className="webhook-variables">
        <p className="webhook-template-body">{template.body}</p>
        <strong>{t("clients.webhooks.variablesLabel")}</strong>
        {slots.length ? <div className="contact-fields-builtin">{slots.map((slot) => <span key={slot} className="pill">{slot}</span>)}</div> : <small className="muted">{t("clients.webhooks.variablesNone")}</small>}
      </div>}
      {error && <Alert>{error}</Alert>}
      <div className="modal-actions">
        <button type="button" className="button" onClick={onClose}>{t("common.cancel")}</button>
        <button className="button primary" disabled={busy || !ready}>{busy ? <LoaderCircle className="spin" size={16} /> : webhook ? t("clients.webhooks.saveChanges") : t("clients.webhooks.create")}</button>
      </div>
    </form>
  </Modal>;
}
