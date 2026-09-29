// The AI provider (must match backend app/services/model_catalog.py).
//
// OpenRouter fronts every vendor behind one key, so an agency configures a
// single key and picks any model by its OpenRouter slug ("openai/gpt-6-luna").
// Models are grouped by what an agency actually chooses on: cost and speed
// versus capability. The first entry is the recommended default, and the
// wizard preselects it so an agent can never be created without a model.
// Group and badge wording is end-user copy and therefore lives in the i18n
// dictionaries, not here. Any other OpenRouter slug still works when typed.

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
    id: "openrouter",
    label: "OpenRouter",
    keyPlaceholder: "sk-or-v1-...",
    keyUrl: "https://openrouter.ai/settings/keys",
    models: [
      { id: "openai/gpt-6-luna", label: "GPT-6 Luna", group: "fast", recommended: true },
      { id: "openai/gpt-5.6-luna", label: "GPT-5.6 Luna", group: "fast" },
      { id: "openai/gpt-4.1-nano", label: "GPT-4.1 nano", group: "fast" },
      { id: "openai/gpt-5.4-nano", label: "GPT-5.4 nano", group: "fast" },
      { id: "google/gemini-3.1-flash-lite", label: "Gemini 3.1 Flash-Lite", group: "fast" },
      { id: "google/gemini-3.5-flash-lite", label: "Gemini 3.5 Flash-Lite", group: "fast" },
      { id: "anthropic/claude-haiku-4.5", label: "Claude Haiku 4.5", group: "fast" },
      { id: "deepseek/deepseek-v4-flash", label: "DeepSeek V4 Flash", group: "fast" },
      { id: "openai/gpt-5.6-terra", label: "GPT-5.6 Terra", group: "balanced" },
      { id: "openai/gpt-4.1-mini", label: "GPT-4.1 mini", group: "balanced" },
      { id: "openai/gpt-5.4-mini", label: "GPT-5.4 mini", group: "balanced" },
      { id: "google/gemini-3.8-flash", label: "Gemini 3.8 Flash", group: "balanced" },
      { id: "google/gemini-3.7-flash", label: "Gemini 3.7 Flash", group: "balanced" },
      { id: "google/gemini-3.6-flash", label: "Gemini 3.6 Flash", group: "balanced" },
      { id: "google/gemini-3.5-flash", label: "Gemini 3.5 Flash", group: "balanced" },
      { id: "anthropic/claude-sonnet-5", label: "Claude Sonnet 5", group: "balanced" },
      { id: "meta-llama/llama-4-maverick", label: "Llama 4 Maverick", group: "balanced" },
      { id: "openai/gpt-6-sol", label: "GPT-6 Sol", group: "capable" },
      { id: "openai/gpt-6-astra", label: "GPT-6 Astra", group: "capable" },
      { id: "openai/gpt-5.6-sol", label: "GPT-5.6 Sol", group: "capable" },
      { id: "openai/gpt-4.1", label: "GPT-4.1", group: "capable" },
      { id: "openai/gpt-5.4", label: "GPT-5.4", group: "capable" },
      { id: "openai/gpt-5.5", label: "GPT-5.5", group: "capable" },
      { id: "anthropic/claude-opus-5", label: "Claude Opus 5", group: "capable" },
      { id: "anthropic/claude-fable-5", label: "Claude Fable 5", group: "capable" },
      { id: "deepseek/deepseek-v4-pro", label: "DeepSeek V4 Pro", group: "capable" },
      { id: "x-ai/grok-4.5", label: "Grok 4.5", group: "capable" },
    ] as const satisfies readonly ModelOption[],
  },
] as const;

export type ProviderId = (typeof PROVIDERS)[number]["id"];

export const DEFAULT_PROVIDER: ProviderId = "openrouter";

// Transcription models for the audio-recognition capability (OpenRouter's
// audio endpoint).
export const AUDIO_MODELS = ["openai/gpt-4o-mini-transcribe", "openai/gpt-4o-transcribe", "openai/gpt-transcribe"] as const;
export const DEFAULT_AUDIO_MODEL = AUDIO_MODELS[0];

// Embedding models for the knowledge base (mirrors the API catalog, used while
// it loads). Vectors from different models are not comparable, so changing an
// agent's model reindexes its documents.
export const EMBEDDING_MODELS = [
  "openai/text-embedding-3-small",
  "openai/text-embedding-3-large",
  "google/gemini-embedding-2",
  "qwen/qwen3-embedding-8b",
  "voyageai/voyage-4",
  "voyageai/voyage-4-lite",
  "mistralai/mistral-embed-2312",
] as const;
export const DEFAULT_EMBEDDING_MODEL = EMBEDDING_MODELS[0];

// Vision models for the image-recognition capability: any chat model that
// accepts images. DeepSeek is text-only, so it is left out.
export const IMAGE_MODELS = [
  "openai/gpt-6-luna", "openai/gpt-6-sol", "openai/gpt-6-astra",
  "openai/gpt-5.6-luna", "openai/gpt-5.6-terra", "openai/gpt-5.6-sol", "openai/gpt-5.5", "openai/gpt-5.4", "openai/gpt-5.4-mini", "openai/gpt-5.4-nano",
  "openai/gpt-4.1", "openai/gpt-4.1-mini", "openai/gpt-4.1-nano",
  "google/gemini-3.8-flash", "google/gemini-3.7-flash", "google/gemini-3.6-flash", "google/gemini-3.5-flash", "google/gemini-3.5-flash-lite", "google/gemini-3.1-flash-lite",
  "anthropic/claude-sonnet-5", "anthropic/claude-opus-5", "anthropic/claude-fable-5", "anthropic/claude-haiku-4.5",
  "x-ai/grok-4.5", "meta-llama/llama-4-maverick",
] as const;
export const DEFAULT_IMAGE_MODEL = "openai/gpt-4.1";

export function providerLabel(id: string): string {
  return PROVIDERS.find((p) => p.id === id)?.label ?? id;
}

// What the API's catalog says about every model OpenRouter serves, loaded by
// useAvailableModels. The static lists above are the seed: they keep the
// curated labels, tiers and the recommended default for the models we know,
// and everything else takes its name and context window from here.
export type LiveModel = { id: string; label: string; provider: string; context_window: number; output_price_per_1k: number };

let liveOptions: ModelOption[] = [];
const liveContext = new Map<string, number>();

// A tier from the list price, so a model the seed does not know still gets a
// tag in the picker.
function tierFor(outputPricePer1k: number): ModelGroup {
  if (outputPricePer1k < 0.002) return "fast";
  if (outputPricePer1k < 0.01) return "balanced";
  return "capable";
}

export function setLiveModels(models: LiveModel[]): void {
  const seeded = new Set<string>(PROVIDERS.flatMap((p) => p.models.map((m) => m.id)));
  liveOptions = models.filter((m) => !seeded.has(m.id)).map((m) => ({ id: m.id, label: m.label, group: tierFor(m.output_price_per_1k) }));
  liveContext.clear();
  for (const m of models) liveContext.set(m.id, m.context_window);
}

export function modelOptionsFor(id: string): readonly ModelOption[] {
  const seed: readonly ModelOption[] = PROVIDERS.find((p) => p.id === id)?.models ?? [];
  return id === DEFAULT_PROVIDER ? [...seed, ...liveOptions] : seed;
}

export function modelsFor(id: string): readonly string[] {
  return modelOptionsFor(id).map((model) => model.id);
}

export function defaultModelFor(id: string): string {
  const options = modelOptionsFor(id);
  return (options.find((model) => model.recommended) ?? options[0])?.id ?? "";
}

/** Human label for a model id, falling back to the id itself. */
export function modelLabel(id: string): string {
  return modelOptionsFor(DEFAULT_PROVIDER).find((model) => model.id === id)?.label ?? id;
}

// ~4 characters per token: same approximation as the backend, for the token
// counter in the agent creation wizard.
export function estimateTokens(text: string): number {
  return Math.ceil(text.length / 4);
}

// Approximate context window (in tokens) per model family, used only for the
// "context window usage" bar. Values are representative, not exact.
export function modelContextWindow(id: string): number {
  // What OpenRouter reports for the model, once the catalog has loaded.
  const live = liveContext.get(id);
  if (live) return live;
  // Slugs are "vendor/model"; the family is readable from the model part.
  const name = id.includes("/") ? id.slice(id.indexOf("/") + 1) : id;
  // Haiku is the one current Claude model still on a 200k window; the rest of
  // the line-up is 1M, so the generic "claude" case must not assume 200k.
  if (name.startsWith("claude-haiku")) return 200_000;
  if (name.startsWith("claude")) return 1_000_000;
  if (name.startsWith("gpt-4.1")) return 1_000_000;
  if (name.startsWith("gpt-6") || name.startsWith("gpt-5.6") || name.startsWith("gpt-5.5")) return 1_000_000;
  if (name.startsWith("gpt-5")) return 400_000;
  if (name.startsWith("gemini") || name.startsWith("deepseek") || name.startsWith("llama")) return 1_000_000;
  if (name.startsWith("grok")) return 500_000;
  return 128_000;
}
