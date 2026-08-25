// Supported AI providers (must match backend app/services/model_catalog.py).
//
// Models are grouped by what an agency actually chooses on: cost and speed
// versus capability. The first entry of each provider is its recommended
// default, and the wizard preselects it so an agent can never be created
// without a model. Group and badge wording is end-user copy and therefore
// lives in the i18n dictionaries, not here.

export type ModelGroup = "fast" | "balanced" | "capable";

export type ModelOption = {
  id: string;
  label: string;
  group: ModelGroup;
  // Marks the provider's default. Exactly one per provider.
  recommended?: boolean;
};

export const PROVIDERS = [
  {
    id: "openai",
    label: "OpenAI",
    keyPlaceholder: "sk-proj-...",
    keyUrl: "https://platform.openai.com/api-keys",
    models: [
      { id: "gpt-5.6-luna", label: "GPT-5.6 Luna", group: "fast", recommended: true },
      { id: "gpt-5.6-terra", label: "GPT-5.6 Terra", group: "balanced" },
      { id: "gpt-5.6-sol", label: "GPT-5.6 Sol", group: "capable" },
      { id: "gpt-4.1-nano", label: "GPT-4.1 nano", group: "fast" },
      { id: "gpt-5.4-nano", label: "GPT-5.4 nano", group: "fast" },
      { id: "gpt-4.1-mini", label: "GPT-4.1 mini", group: "balanced" },
      { id: "gpt-5.4-mini", label: "GPT-5.4 mini", group: "balanced" },
      { id: "gpt-4.1", label: "GPT-4.1", group: "capable" },
      { id: "gpt-5.4", label: "GPT-5.4", group: "capable" },
      { id: "gpt-5.5", label: "GPT-5.5", group: "capable" },
    ] as const satisfies readonly ModelOption[],
  },
  {
    id: "anthropic",
    label: "Anthropic",
    keyPlaceholder: "sk-ant-...",
    keyUrl: "https://console.anthropic.com/settings/keys",
    models: [
      { id: "claude-sonnet-5", label: "Claude Sonnet 5", group: "balanced", recommended: true },
      { id: "claude-haiku-4-5", label: "Claude Haiku 4.5", group: "fast" },
      { id: "claude-opus-5", label: "Claude Opus 5", group: "capable" },
      { id: "claude-fable-5", label: "Claude Fable 5", group: "capable" },
      { id: "claude-sonnet-4-6", label: "Claude Sonnet 4.6", group: "balanced" },
      { id: "claude-opus-4-8", label: "Claude Opus 4.8", group: "capable" },
    ] as const satisfies readonly ModelOption[],
  },
] as const;

export type ProviderId = (typeof PROVIDERS)[number]["id"];

// Transcription models for the audio-recognition capability. OpenAI only: no
// current Claude model accepts audio input.
export const AUDIO_MODELS = ["gpt-transcribe", "whisper-1", "gpt-4o-transcribe", "gpt-4o-mini-transcribe", "gpt-4o-transcribe-diarize"] as const;

// Vision-capable models for the image-recognition capability. Every current
// model of both providers accepts image input.
export const IMAGE_MODELS = ["gpt-5.6-luna", "gpt-5.6-terra", "gpt-5.6-sol", "gpt-4.1", "gpt-4.1-mini", "gpt-5.5", "gpt-5.4", "claude-sonnet-5", "claude-haiku-4-5", "claude-opus-5"] as const;

export function providerLabel(id: string): string {
  return PROVIDERS.find((p) => p.id === id)?.label ?? id;
}

export function modelOptionsFor(id: string): readonly ModelOption[] {
  return PROVIDERS.find((p) => p.id === id)?.models ?? [];
}

export function modelsFor(id: string): readonly string[] {
  return modelOptionsFor(id).map((model) => model.id);
}

export function defaultModelFor(id: string): string {
  const options = modelOptionsFor(id);
  return (options.find((model) => model.recommended) ?? options[0])?.id ?? "";
}

export function modelLabel(id: string): string {
  for (const provider of PROVIDERS) {
    const found = provider.models.find((model) => model.id === id);
    if (found) return found.label;
  }
  return id;
}

// ~4 characters per token: same approximation as the backend, for the token
// counter in the agent creation wizard.
export function estimateTokens(text: string): number {
  return Math.ceil(text.length / 4);
}

// Approximate context window (in tokens) per model family, used only for the
// "context window usage" bar. Values are representative, not exact.
export function modelContextWindow(id: string): number {
  // Haiku is the one current Claude model still on a 200k window; the rest of
  // the line-up is 1M, so the generic "claude" case must not assume 200k.
  if (id === "claude-haiku-4-5" || id.startsWith("claude-haiku")) return 200_000;
  if (id.startsWith("claude")) return 1_000_000;
  if (id.startsWith("gpt-4.1")) return 1_000_000;
  if (id.startsWith("gpt-5.6") || id.startsWith("gpt-5.5")) return 1_000_000;
  if (id.startsWith("gpt-5")) return 400_000;
  return 128_000;
}
