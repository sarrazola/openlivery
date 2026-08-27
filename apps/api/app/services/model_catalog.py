"""AI model catalog with metadata (backend source of truth).

Each model declares its context window, capabilities (tools/vision) and price
per 1k tokens. This metadata powers:
- the model picker and token counter in the agent creation wizard,
- the per-model cost figures the catalog API exposes to clients.

IDs are kept in sync with `apps/web/lib/providers.ts` (same identifiers per
provider). Keep both in sync when adding models.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelInfo:
    id: str
    provider: str
    label: str
    family: str
    context_window: int
    max_output_tokens: int
    supports_tools: bool
    supports_vision: bool
    # Provider price per 1,000 tokens, in USD.
    input_price_per_1k: float
    output_price_per_1k: float
    badge: str = ""
    note: str = ""


# Standard approximation to estimate tokens without a tokenizer: ~4 chars/token.
CHARS_PER_TOKEN = 4


_MODELS: tuple[ModelInfo, ...] = (
    # OpenAI
    ModelInfo("gpt-5.6-luna", "openai", "GPT-5.6 Luna", "gpt-5.6", 1_050_000, 128_000, True, True,
              0.0002, 0.0012, "Most affordable", "High volume, chat and cost-sensitive automations."),
    ModelInfo("gpt-5.6-terra", "openai", "GPT-5.6 Terra", "gpt-5.6", 1_050_000, 128_000, True, True,
              0.002, 0.012, "Balanced", "A good balance of capability, speed and price."),
    ModelInfo("gpt-5.6-sol", "openai", "GPT-5.6 Sol", "gpt-5.6", 1_050_000, 128_000, True, True,
              0.004, 0.02, "Top capability", "Complex work and more demanding responses."),
    ModelInfo("gpt-5.6", "openai", "GPT-5.6", "gpt-5.6", 1_050_000, 128_000, True, True,
              0.004, 0.02, "Alias of Sol", "Official alias pointing to the GPT-5.6 Sol model."),
    ModelInfo("gpt-5.5", "openai", "GPT-5.5", "gpt-5.5", 1_050_000, 128_000, True, True,
              0.005, 0.03, "Previous generation", "Available for compatibility and gradual migrations."),
    ModelInfo("gpt-5.4", "openai", "GPT-5.4", "gpt-5.4", 1_050_000, 128_000, True, True,
              0.0025, 0.015, "Previous generation", "Superseded by GPT-5.6 Terra at a lower price."),
    ModelInfo("gpt-5.4-mini", "openai", "GPT-5.4 mini", "gpt-5.4", 400_000, 128_000, True, True,
              0.00075, 0.0045, "Previous generation", "Mid-tier option from the previous family."),
    ModelInfo("gpt-5.4-nano", "openai", "GPT-5.4 nano", "gpt-5.4", 400_000, 128_000, True, True,
              0.0002, 0.00125, "Previous generation", "Superseded by GPT-5.6 Luna."),
    ModelInfo("gpt-4.1", "openai", "GPT-4.1", "gpt-4.1", 1_047_576, 32_768, True, True,
              0.002, 0.008, "No reasoning step", "Lower latency for instruction following and tool calls."),
    ModelInfo("gpt-4.1-mini", "openai", "GPT-4.1 mini", "gpt-4.1", 1_047_576, 32_768, True, True,
              0.0004, 0.0016, "No reasoning step", "Economical option with a wide context window."),
    ModelInfo("gpt-4.1-nano", "openai", "GPT-4.1 nano", "gpt-4.1", 1_047_576, 32_768, True, True,
              0.0001, 0.0004, "Most affordable", "The lowest-cost text model in the line-up."),
    # Google Gemini
    ModelInfo("gemini-3.6-flash", "google", "Gemini 3.6 Flash", "gemini-3", 1_000_000, 65_536, True, True,
              0.0003, 0.0025, "Current", "Fast, balanced model for agents and applications."),
    ModelInfo("gemini-3.5-flash", "google", "Gemini 3.5 Flash", "gemini-3", 1_000_000, 65_536, True, True,
              0.0003, 0.0025, "Stable", "General low-latency option with a wide context."),
    ModelInfo("gemini-3.5-flash-lite", "google", "Gemini 3.5 Flash-Lite", "gemini-3", 1_000_000, 65_536, True, False,
              0.0001, 0.0004, "Economical", "The lowest-cost alternative in the Gemini 3.5 family."),
    ModelInfo("gemini-3.1-pro-preview", "google", "Gemini 3.1 Pro Preview", "gemini-3", 1_000_000, 65_536, True, True,
              0.00125, 0.01, "Preview", "Advanced reasoning; try it first in controlled tests."),
    # Anthropic
    ModelInfo("claude-sonnet-5", "anthropic", "Claude Sonnet 5", "claude", 1_000_000, 128_000, True, True,
              0.002, 0.01, "Balanced", "A mix of speed and intelligence for production."),
    ModelInfo("claude-opus-5", "anthropic", "Claude Opus 5", "claude", 1_000_000, 128_000, True, True,
              0.005, 0.025, "Top capability", "Complex tasks, reasoning and demanding agent flows."),
    ModelInfo("claude-fable-5", "anthropic", "Claude Fable 5", "claude", 1_000_000, 128_000, True, True,
              0.01, 0.05, "Maximum capability", "Deep research and long autonomous runs."),
    ModelInfo("claude-haiku-4-5", "anthropic", "Claude Haiku 4.5", "claude", 200_000, 8_192, True, True,
              0.001, 0.005, "Fast", "Quick responses and simpler workloads."),
    ModelInfo("claude-sonnet-4-6", "anthropic", "Claude Sonnet 4.6", "claude", 1_000_000, 16_384, True, True,
              0.003, 0.015, "Previous generation", "Superseded by Sonnet 5, which costs less."),
    ModelInfo("claude-opus-4-8", "anthropic", "Claude Opus 4.8", "claude", 1_000_000, 32_768, True, True,
              0.005, 0.025, "Previous generation", "Superseded by Opus 5 at the same price."),
    # DeepSeek
    ModelInfo("deepseek-v4-flash", "deepseek", "DeepSeek V4 Flash", "deepseek-v4", 1_000_000, 16_384, True, False,
              0.0002, 0.0009, "Economical", "High-volume chat and agents with up to 1M context."),
    ModelInfo("deepseek-v4-pro", "deepseek", "DeepSeek V4 Pro", "deepseek-v4", 256_000, 16_384, True, False,
              0.0006, 0.0025, "Advanced", "Reasoning, code and complex long-running flows."),
    # xAI
    ModelInfo("grok-4.5", "xai", "Grok 4.5", "grok-4", 256_000, 32_768, True, True,
              0.003, 0.015, "Current", "xAI's main model for code, agents and general work."),
    ModelInfo("grok-4.3", "xai", "Grok 4.3", "grok-4", 131_072, 16_384, True, False,
              0.001, 0.005, "Economical", "A lower-priced alternative with a wide context window."),
    # Groq (open source)
    ModelInfo("openai/gpt-oss-20b", "groq", "GPT-OSS 20B", "gpt-oss", 131_072, 8_192, True, False,
              0.0001, 0.0005, "Very fast", "High-volume production at lower cost on Groq."),
    ModelInfo("openai/gpt-oss-120b", "groq", "GPT-OSS 120B", "gpt-oss", 131_072, 16_384, True, False,
              0.00075, 0.003, "More capable", "The most capable open model available on Groq."),
    ModelInfo("qwen/qwen3.6-27b", "groq", "Qwen 3.6 27B", "qwen3", 131_072, 16_384, True, False,
              0.0002, 0.0008, "Current", "A recent option for reasoning and general generation."),
    # OpenRouter (routes to models already listed)
    ModelInfo("openai/gpt-5.6-luna", "openrouter", "GPT-5.6 Luna", "gpt-5.6", 1_050_000, 128_000, True, True,
              0.0002, 0.0012, "Economical", "OpenRouter route to OpenAI's efficient model."),
    ModelInfo("anthropic/claude-sonnet-5", "openrouter", "Claude Sonnet 5", "claude", 1_000_000, 128_000, True, True,
              0.002, 0.01, "Balanced", "OpenRouter route to the current Sonnet model."),
    ModelInfo("google/gemini-3.6-flash", "openrouter", "Gemini 3.6 Flash", "gemini-3", 1_000_000, 65_536, True, True,
              0.0003, 0.0025, "Fast", "OpenRouter route to Google's current Flash model."),
    ModelInfo("deepseek/deepseek-v4-flash", "openrouter", "DeepSeek V4 Flash", "deepseek-v4", 1_000_000, 16_384, True, False,
              0.0002, 0.0009, "Economical", "OpenRouter route to DeepSeek's efficient model."),
)

_BY_ID: dict[str, ModelInfo] = {model.id: model for model in _MODELS}


def list_models() -> list[ModelInfo]:
    """All catalog models, in declaration order."""
    return list(_MODELS)


def get_model(model_id: str) -> ModelInfo | None:
    """Metadata for a model by its ID, or None if not in the catalog."""
    return _BY_ID.get(model_id)


def estimate_tokens(text: str) -> int:
    """Quick token estimate (~4 characters per token)."""
    return (len(text) + CHARS_PER_TOKEN - 1) // CHARS_PER_TOKEN
