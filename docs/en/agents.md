# Agents

> Leer en español: [agents.md](../es/agents.md)

An agent is the AI assistant that talks to your end users. Every agent belongs to a single client, and each agent carries its own instructions, model choice, knowledge and multimodal settings. This page covers how to create one and what each setting does.

## What an agent is

An agent lives under a client (`Agency → Client → Agent`). The client is only the identity of the business: its name, its industry and its business type, picked from a fixed catalog. Everything about what the business does and how it should be answered is written on the agent, so two agents of the same client can describe it differently. An agent defines how it should behave, which provider and model answer its messages, how much conversation history it remembers, and whether it can understand incoming images and audio. You can create as many agents per client as you need — for example one for WhatsApp and another embedded as a web widget.

## Creating an agent with the wizard

New agents are created through a five-step wizard (**Agents → New agent**):

1. **Template** — start from scratch (recommended and preselected) or pick an industry starter template. Templates pre-fill what the agent does, its tone and the business brief (what the business does, products, audience, key info, always and never) in your language, for you to replace the specifics with the client's own.
2. **Identity** — choose the owning client and name the agent.
3. **Instructions** — write what the agent does and how it should sound. A live token counter estimates the size of the prompt as you type.
4. **Model** — set the timezone, provider and model, and tune temperature, max tokens and memory. A context-window bar shows how much of the model's window the prompt uses.
5. **Review** — confirm the summary and create the agent.

The built-in starter templates are Restaurant orders, Real estate leads, Clinic appointments, Online store support and Customer support. After creation you refine everything on the agent detail page, where **Basics** holds the client, name, business brief, the agent's job, escalation and model. The model section shows how many tokens the composed prompt costs on every message. Creating a client ends on the wizard with that client preselected.

## Choosing a provider and model

Each agent uses one provider — `openai` or `anthropic` — and one model from that provider. The agency's stored API key for that provider is used, so add your keys first. See [AI providers](ai-providers.md) for the available models and how keys are configured. The model field accepts a custom value if you run a model that isn't in the preset list.

## Multimodal capabilities

An agent understands incoming media out of the box: both capabilities are on for new agents. Each has its own toggle and its own model setting, independent of the main chat model, under the advanced options of the model section:

- **Image recognition (vision)** — when `image_enabled` is on, inbound images are described by the model in `image_model` before reaching the agent.
- **Audio transcription** — when `audio_enabled` is on, inbound audio is transcribed by the model in `audio_model` (default `whisper-1`) before reaching the agent.

Both features use OpenAI models, so they require an OpenAI key regardless of the agent's chat provider.

## Agent settings

| Setting | Field | What it does |
| --- | --- | --- |
| Client | `client_id` | The client that owns the agent. |
| What the agent does | `instructions` | Its job, tasks and rules, in prose. Sent as part of the system prompt. |
| Tone | `personality` | Tone and style guidance for replies. |
| Business brief | `brief_summary`, `brief_products`, `brief_audience`, `brief_policies`, `brief_dos`, `brief_donts` | What the business is and offers, plus the agent's always/never rules. Composed into the system prompt. |
| Business identity | `industry`, `business_type`, `business_custom` (on the client) | Catalog codes (`GET /api/industries`) that name the kind of business in the prompt's first line; when the catalog only offers "other", `business_custom` holds the client's own words. |
| Prompt language | `prompt_language` | `es` or `en`: the language of the prompt's headings and fixed sentences. Set from the UI language when the agent is saved. |
| Timezone | `timezone` | IANA timezone (e.g. `America/Bogota`) injected so the agent knows the local date and time. Defaults to `UTC`. |
| Provider | `provider` | `openai` or `anthropic`. |
| Model | `model` | The chat model used for replies. |
| Temperature | `temperature` | Sampling randomness, `0.0`–`2.0` (default `0.7`). |
| Max tokens | `max_tokens` | Maximum tokens per reply, `1`–`32000` (default `2048`). |
| Memory limit | `memory_limit` | How many past messages are kept as conversation memory, `0`–`200` (default `30`). |
| Image recognition | `image_enabled`, `image_model` | Enable vision and pick the model that describes inbound images. |
| Audio transcription | `audio_enabled`, `audio_model` | Enable transcription and pick the model that transcribes inbound audio (default `whisper-1`). |

Sampling parameters are applied best-effort; models that reject a value fall back to their own defaults.

## Knowledge in the system prompt

Beyond these settings, the agent's Q&A pairs, uploaded documents, per-client context and per-agent context are all assembled into the system prompt at answer time. See [Knowledge base](knowledge-base.md) for how documents are chunked, embedded and retrieved.
