# AI providers

> Leer en español: [ai-providers.md](../es/ai-providers.md)

OpenLivery does not ship with an AI provider of its own. Each agency brings its own key: you paste an **OpenRouter** API key, OpenLivery stores it encrypted, and every agent under that agency uses it to talk to any model OpenRouter offers. This keeps you in control of billing, quotas and data, and gives every agent the same door to OpenAI, Anthropic, Google, DeepSeek, xAI and the rest.

## Bring your own key

Keys are configured per agency. Open **Settings**, find the OpenRouter card and paste your key (create one at [openrouter.ai/settings/keys](https://openrouter.ai/settings/keys)). When you save it, OpenLivery first validates the key against OpenRouter (it asks `{base_url}/key`, which describes the key and its remaining credit); if the check fails, nothing is stored. Only after a successful validation is the key persisted.

Stored keys are never returned to the browser in full — the UI only shows a masked value. On disk, the key is encrypted with a key derived from `ENCRYPTION_KEY` and decrypted on demand when an agent needs it, so rotating or losing that secret makes the stored key unreadable. See [Configuration](configuration.md) for how `ENCRYPTION_KEY` is set and why it must never change.

## How requests are made

OpenLivery calls OpenRouter's OpenAI-compatible API at `https://openrouter.ai/api/v1`:

| Capability | Endpoint |
| --- | --- |
| Chat replies and tool calls | `/chat/completions` |
| Image understanding | `/chat/completions` with an image part |
| Voice note transcription | `/audio/transcriptions` |
| Knowledge base embeddings | `/embeddings` (`openai/text-embedding-3-small`) |

Every chat reply comes back with OpenRouter's usage block, including what the call cost. OpenLivery stores that figure with the reply's usage record (`usage_records.cost_usd`), so cost reporting reads real numbers instead of estimating from a price table.

## Model ids

Models are named by their OpenRouter slug, `vendor/model`: `openai/gpt-6-luna`, `anthropic/claude-sonnet-5`, `google/gemini-3.8-flash`. The agent wizard and the agent page offer a curated preset list, grouped by what an agency actually chooses on (fastest and cheapest, balanced, most capable), and accept any other slug typed by hand. The presets come from `apps/web/lib/providers.ts` and are mirrored, with context windows, capabilities and list prices, in `apps/api/app/services/model_catalog.py` (`GET /api/catalog/models`).

### Vision and audio models

Some capabilities use dedicated model sets rather than the chat model:

- **Vision (`IMAGE_MODELS`)** for image understanding: any vision-capable chat model in the catalog. The default is `openai/gpt-4.1`.
- **Transcription (`AUDIO_MODELS`)** for audio understanding: `openai/gpt-4o-mini-transcribe` (default), `openai/gpt-4o-transcribe`, `openai/gpt-transcribe`.

## Choosing a model per agent

The key is set once per agency, but each agent picks its own model. You do this when you create or edit an agent, choosing from the presets above or typing a slug. See [Agents](agents.md) for how model choice, instructions and knowledge come together.

## Upgrading from OpenAI and Anthropic keys

Releases before migration `0042_openrouter` stored OpenAI and Anthropic keys and used bare model ids. The migration moves every agent to OpenRouter and rewrites its model ids to slugs (`gpt-4.1-mini` becomes `openai/gpt-4.1-mini`, `claude-sonnet-5` becomes `anthropic/claude-sonnet-5`, `whisper-1` becomes `openai/gpt-4o-mini-transcribe`). The old keys are dropped, since OpenRouter cannot use them: after upgrading, add an OpenRouter key in Settings and the agents reply again.

## Next steps

- [Agents](agents.md) — pick a model and write instructions.
- [Configuration](configuration.md) — `ENCRYPTION_KEY` and other secrets.
- [Knowledge base](knowledge-base.md) — give an agent context, Q&A and PDFs.
