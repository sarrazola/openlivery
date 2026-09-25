# Agents

> Leer en español: [agents.md](../es/agents.md)

An agent is the AI assistant that talks to your end users. Every agent belongs to a single client, and each agent carries its own instructions, model choice, knowledge and multimodal settings. This page covers how to create one and what each setting does.

## What an agent is

An agent lives under a client (`Agency → Client → Agent`). The client is only the identity of the business: its name, its industry and its business type, picked from a fixed catalog. Everything about what the business does and how it should be answered is written on the agent, so two agents of the same client can describe it differently. An agent defines how it should behave, which provider and model answer its messages, how much conversation history it remembers, and whether it can understand incoming images and audio. You can create as many agents per client as you need — for example one for WhatsApp and another embedded as a web widget.

## Creating an agent with the wizard

New agents are created through a five-step wizard (**Agents → New agent**); the step header is clickable to move between steps already reached:

1. **Template** — start from scratch (recommended and preselected) or pick an industry starter template. Templates pre-fill what the agent does, its tone and the business brief (what the business does, products, audience, key info, always and never) in your language, for you to replace the specifics with the client's own.
2. **Identity** — choose the owning client and name the agent.
3. **Essentials** — the three things the agent needs to answer well: what the business does, its key info and policies, and what the agent does. Products, audience, always/never rules and tone are filled in afterwards on the agent's Basics.
4. **Model** — provider and model, with the recommended model preselected and each option tagged (recommended, balanced, most capable), plus, under advanced options, generation settings and the image and audio capabilities.
5. **Review** — a summary of the agent and the size of its prompt, and the create button. Creating lands on the agent's Basics.

The built-in starter templates are Restaurant orders, Real estate leads, Clinic appointments, Online store support and Customer support. After creation you refine everything on the agent detail page, where **Basics** holds the client, name, business brief, the agent's job, escalation and model. The model section shows how many tokens the composed prompt costs on every message. Creating a client ends on the wizard with that client preselected.

## Choosing a model

Each agent picks one model by its OpenRouter slug (`openai/gpt-5.6-luna`, `anthropic/claude-sonnet-5`, `google/gemini-3.8-flash`). The agency's stored OpenRouter key is used, so add it first. See [AI providers](ai-providers.md) for the available models and how the key is configured. The model field accepts any slug typed by hand if the model you want isn't in the preset list.

## Multimodal capabilities

An agent understands incoming media out of the box: both capabilities are on for new agents. Each has its own toggle and its own model setting, independent of the main chat model, under the advanced options of the model section:

- **Image recognition (vision)** — when `image_enabled` is on, inbound images are described by the model in `image_model` before reaching the agent.
- **Audio transcription** — when `audio_enabled` is on, inbound audio is transcribed by the model in `audio_model` (default `openai/gpt-4o-mini-transcribe`) before reaching the agent.

Both features go through the same OpenRouter key as the chat model.

## Agent settings

| Setting | Field | What it does |
| --- | --- | --- |
| Client | `client_id` | The client that owns the agent. |
| What the agent does | `instructions` | Its job, tasks and rules, in prose. Sent as part of the system prompt. |
| Tone | `personality` | Tone and style guidance for replies. |
| Business brief | `brief_summary`, `brief_products`, `brief_audience`, `brief_policies`, `brief_dos`, `brief_donts` | What the business is and offers, plus the agent's always/never rules. Composed into the system prompt. |
| Business identity | `industry`, `business_type`, `business_custom` (on the client) | Catalog codes (`GET /api/industries`) that name the kind of business in the prompt's first line; when the catalog only offers "other", `business_custom` holds the client's own words. |
| Contact | from the conversation | Name, phone, e-mail, custom fields, tags and channel of the person writing, added to the prompt at reply time so a form, an e-mail or a tool gets them instead of "not specified". Only what the contact record has is listed. Absent in the playground. |
| Contact details to collect | `capture_enabled`, `GET`/`PUT /api/agents/{id}/capture` | What the agent asks the customer for and saves on the contact. See [Collecting contact details](#collecting-contact-details). |
| Prompt language | `prompt_language` | `es` or `en`: the language of the prompt's headings and fixed sentences. Set from the UI language when the agent is saved. |
| Timezone | `timezone` (on the client) | IANA timezone of the business (e.g. `America/Bogota`), injected so every agent of the client knows the local date and time. Set on the client, defaults to `UTC`. |
| Provider | `provider` | Always `openrouter`. |
| Model | `model` | The chat model used for replies, as an OpenRouter slug. |
| Temperature | `temperature` | Sampling randomness, `0.0`–`2.0` (default `0.7`). |
| Max tokens | `max_tokens` | Maximum tokens per reply, `1`–`32000` (default `2048`). |
| Memory limit | `memory_limit` | How many past messages are kept as conversation memory, `0`–`200` (default `30`). |
| Reply delay | `reply_delay_min_seconds`, `reply_delay_max_seconds` | Quiet window before the agent answers a WhatsApp message, drawn at random between the two bounds, `0`–`60` seconds each (default `6` to `9`). The window restarts with each new visitor message, so a burst gets one reply. Both at `0` answer every message immediately. The maximum must be greater than or equal to the minimum. |
| Image recognition | `image_enabled`, `image_model` | Enable vision and pick the model that describes inbound images. |
| Audio transcription | `audio_enabled`, `audio_model` | Enable transcription and pick the model that transcribes inbound audio (default `whisper-1`). |

Sampling parameters are applied best-effort; models that reject a value fall back to their own defaults.

## Collecting contact details

An agent can ask the customer for details and save them on the contact, so the
next conversation with that person already has them and the agent does not ask
again. Under **Contact details** in the agent's settings, switch it on and pick
the fields: the built-in name, e-mail and phone, or any custom field the client
defined, and optionally the channels each applies to (WhatsApp, Instagram,
Messenger, web chat); with none picked it applies everywhere. What a field is
and when to ask for it is the field's own description, so every agent of the
client asks the same way; the built-in three carry one of their own.

Custom fields belong to the client and are shared by every agent and the client
portal: **Contact fields** on the client page (`/api/clients/{id}/contact-fields`).
A field has a `snake_case` key the agent and the API use (it cannot change
later), a label people see, a type (text, number, e-mail, phone) the value is
validated against, and a description that tells the agent what the value is and
when to ask for it. Deleting a field removes it from every agent and clears its
value from every contact that held one.

At reply time, only the fields still unknown for that contact reach the prompt,
as a "Details to collect" section with their descriptions, and the agent gets a
`save_contact_field` tool. The rule it follows: ask naturally, one at a time,
never as a form, and save only what the customer stated explicitly. Built-in
values go to the contact's own columns; custom values to `attributes` on the
contact, which the portal shows and edits on the contact card
(`PATCH /api/portal/{slug}/contacts/{id}` with `attributes`). A phone another
contact already holds is not overwritten. The playground rehearses the fields
without saving anything.

## Business hours and future requests

Put the schedule in the agent's **Key information and policies** (`brief_policies`) and set the client's timezone. The prompt includes the current local weekday, date and time. Policies travel with every reply, even when no document is retrieved.

Describe service hours separately from what the assistant may do outside those hours. A clinic's reception being closed at 01:00 does not mean the assistant must stop answering or cannot book an available appointment for tomorrow. A restaurant may answer menu questions all night while accepting immediate orders only during kitchen hours. Specify delivery and pickup hours, last-order cutoffs, holidays, overnight shifts and whether scheduled orders are permitted where relevant.

For example, a clinic policy could say:

> Reception and consultations: Monday to Friday, 09:00-17:00, America/Bogota. Online booking is available at any time for future slots returned by the booking tool. Check the requested slot and record the appointment before saying it is booked. If booking is unavailable, explain that the request is unconfirmed.

A restaurant could instead say:

> Kitchen: Monday to Saturday, 18:00-23:00; last order at 22:30. Delivery: 18:00-22:30. Answer menu questions at any time. Outside ordering hours, offer a scheduled order only if the ordering system accepts it. Reviewing the order with the customer does not mean it has been accepted.

Use the business's actual rules, not these example hours. Confirming a new appointment, reservation or order requires a successful result from the tool that records it. Without that tool, the assistant can collect a request when allowed, but must explain that it remains unconfirmed.

These are instructions for the model, not a server-side schedule validator. A tool that records bookings or orders must enforce the requested service time, availability and exceptions itself when those rules must be guaranteed. Merely enabling an unrelated tool does not give the assistant access to a calendar.

## Knowledge in the system prompt

Beyond these settings, the agent's Q&A pairs, uploaded documents, per-client context and per-agent context are all assembled into the system prompt at answer time. See [Knowledge base](knowledge-base.md) for how documents are chunked, embedded and retrieved.

## Unpublishing and deleting an agent

**Unpublish** (`is_active: false`) pauses the agent: it stops answering and spending tokens, messages keep arriving for a person, and everything is kept. **Delete** (`DELETE /api/agents/{id}`) removes its knowledge, tools, questions and answers, escalation rules and configuration. The conversations it handled are the client's history and stay in the portal under the agent's name. An agent that answers a channel cannot be deleted until another agent is assigned to that channel (`409`).
