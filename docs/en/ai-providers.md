# AI providers

> Leer en español: [ai-providers.md](../es/ai-providers.md)

OpenLivery does not ship with an AI provider of its own. Instead, each agency brings its own key: you paste an API key for a supported provider, OpenLivery stores it encrypted, and every agent under that agency uses it to talk to a model. This keeps you in control of billing, quotas and data.

## Bring your own key

Keys are configured per agency, one key per provider. Open **Settings**, find the provider card and paste your key. When you save it, OpenLivery first validates the key against the provider (it lists `{base_url}/models`); if the check fails, nothing is stored. Only after a successful validation is the key persisted.

Stored keys are never returned to the browser in full — the UI only shows a masked value. On disk, the key is encrypted with a key derived from `ENCRYPTION_KEY` and decrypted on demand when an agent needs it, so rotating or losing that secret makes every stored key unreadable. See [Configuration](configuration.md) for how `ENCRYPTION_KEY` is set and why it must never change.

## Supported providers

Two providers are supported out of the box, each with a fixed base URL:

| Provider | Base URL | Example models |
| --- | --- | --- |
| OpenAI | `https://api.openai.com/v1` | `gpt-5.6-sol`, `gpt-5.4-mini`, `gpt-4.1` |
| Anthropic | `https://api.anthropic.com/v1` | `claude-opus-4-8`, `claude-sonnet-4-6`, `claude-haiku-4-5` |

OpenAI keys are sent as a bearer token; Anthropic keys use the `x-api-key` header with the `anthropic-version` header. Under the hood OpenLivery calls the OpenAI Responses API and the Anthropic Messages API.

### Any OpenAI-compatible endpoint

The `base_url` and `model` are per-connection settings, so any OpenAI-compatible endpoint works. Connection testing simply performs a `GET` on `{base_url}/models` and reports how many models the key can see. As long as your endpoint speaks the OpenAI (or Anthropic) API and exposes a `/models` list, you can point OpenLivery at it.

## Model presets

The Settings UI and the agent wizard offer preset model lists so you don't have to memorize IDs. These come straight from `apps/web/lib/providers.ts`.

**OpenAI:** `gpt-5.6-sol`, `gpt-5.6-terra`, `gpt-5.6-luna`, `gpt-5.5`, `gpt-5.4`, `gpt-5.4-mini`, `gpt-5.4-nano`, `gpt-5.2`, `gpt-5.1`, `gpt-5`, `gpt-5-mini`, `gpt-5-nano`, `gpt-4.1`, `gpt-4.1-mini`, `gpt-4.1-nano`.

**Anthropic:** `claude-opus-4-8`, `claude-opus-4-7`, `claude-opus-4-6`, `claude-sonnet-4-6`, `claude-sonnet-4-5`, `claude-haiku-4-5`.

### Vision and audio models

Some capabilities use dedicated model sets rather than the chat model:

- **Vision (`IMAGE_MODELS`)** for image understanding: `gpt-5.6-sol`, `gpt-5.6-terra`, `gpt-4.1`, `gpt-4.1-mini`, `gpt-5.5`, `gpt-5.4`, `gpt-5`, `gpt-5-mini`.
- **Transcription (`AUDIO_MODELS`)** for audio understanding: `gpt-transcribe`, `whisper-1`, `gpt-4o-transcribe`, `gpt-4o-mini-transcribe`, `gpt-4o-transcribe-diarize`.

## Choosing a model per agent

The provider key is set once per agency, but each agent picks its own provider and model. You do this when you create or edit an agent, choosing from the presets above (or typing a custom ID for a compatible endpoint). See [Agents](agents.md) for how model choice, instructions and knowledge come together.

## Next steps

- [Agents](agents.md) — pick a model and write instructions.
- [Configuration](configuration.md) — `ENCRYPTION_KEY` and other secrets.
- [Knowledge base](knowledge-base.md) — give an agent context, Q&A and PDFs.
