# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
The three services (`apps/api`, `apps/web`, `apps/whatsapp`) share a single version
and are released together.

## [Unreleased]

Upgrading: this release adds a database migration (applied automatically by the
Docker stack; run `alembic upgrade head` on local setups). The api image now
bundles ffmpeg for voice-note transcoding.

### Added

- Debounced WhatsApp replies: instead of answering every message the moment it
  arrives, the assistant now waits for a quiet window (8 seconds by default,
  `REPLY_DEBOUNCE_SECONDS`) that restarts with each new visitor message, then
  answers the whole burst with a single reply — the way a person reads a run of
  messages before responding. Applies to both WhatsApp channels (Baileys bridge
  and Cloud API); set the window to `0` to restore the immediate
  one-reply-per-message behaviour. No schema change.
- Connection guides under `docs/connections/`: a step-by-step WhatsApp
  Business Cloud API setup guide (Meta app, phone number, permanent access
  token, app secret, webhook, go-live and troubleshooting), in English and
  Spanish, linked from the README.
- Mobile app for the client of an agency (`apps/mobile`, Expo/React Native, iOS
  and Android). Sign in with a server address plus the portal credentials the
  agency issued, and the business gets its conversations on a phone: read, take
  over from the assistant, reply. The agency's colour and logo arrive with the
  session, so one build serves every agency, and `brands/` plus a required
  `BRAND` at build time let an agency publish its own from the same source.
  It is not part of a server install and nothing else imports it - see
  `apps/mobile/README.md`.
- `POST /api/mobile/sign-in` and `GET /api/mobile/session`, which resolve a
  portal from its credentials and issue a bearer token. Portal routes accept
  that token alongside the cookie they already accepted, because a native client
  cannot rely on cookies surviving a restart. No schema change.

- Chat attachments across every channel (playground, agency inbox, client
  portal, widget, WhatsApp QR and WhatsApp Cloud API): images, voice notes,
  videos and files are persisted and rendered as real chat media instead of
  being flattened into text. The LLM keeps receiving text — transcripts and
  image descriptions are stored separately (`messages.llm_content`) so agents
  keep full context after a human takeover, including media sent by the
  operator.
- Operator media replies from the Inbox and the client portal: attach files,
  drag & drop with a pending-attachment preview, and record voice notes with a
  microphone button. Outbound audio is transcoded to ogg/opus (ffmpeg) with
  its duration so WhatsApp delivers it as a playable voice note; images,
  videos and documents are delivered through both WhatsApp channels.
- WhatsApp-style chat media UI: image lightbox with prev/next navigation over
  the whole conversation, multi-image grid with a "+N" overlay, inline video
  player, and a custom voice-note player (real waveform, click-to-seek,
  1x/1.5x/2x speed).
- "Shared content" drawer (Media / Links / Docs) in the Inbox and the client
  portal conversation headers.
- Lightweight markdown rendering in chat bubbles (bold, italics, code, lists,
  links) and clickable bare URLs.
- Client portal inbox parity with the agency inbox: search, Human/AI filter
  tabs, channel badges and readable channel labels.
- Widget file uploads (rate limited) and attachment rendering.
- Inbound WhatsApp videos (QR and Cloud API) are now stored and shown; they
  previously only contributed their caption.
- Chat widget polish: a greeting teaser bubble (using the agent's configured
  greeting) and an unread-count badge on the launcher, message timestamps in
  the bubbles, and a button for the visitor to download their own conversation
  as a text transcript. The embed's iframe now also allows the microphone.
- Per-client logo: upload a logo on the client's details page (PNG, JPG, WebP
  or SVG, up to 2 MB); it is shown in that client's chat widget and portal
  inbox, falling back to the agency logo. Logos are served with
  `X-Content-Type-Options: nosniff` and a locked-down `Content-Security-Policy`
  so an SVG logo cannot execute script when its URL is opened directly.
- Discord community link in the agency sidebar ("Join the community" /
  "Unirse a la comunidad"), opening the project Discord server in a new tab.
- Public `GET /api/auth/status` endpoint reporting whether the instance still
  needs its first agency and whether registration is open. The login page uses
  it to open straight into first-run setup on an empty database and to hide
  the register tab afterwards.

### Changed

- Portal sign-in is now only through portal users, managed from a new "Portal
  access" section on the client's portal tab (add, suspend, reactivate,
  remove). The shared email/password pair on the client is gone, closing the
  gap where credentials saved through the old form never appeared in the
  portal user list. Upgrading: the migration carries any remaining shared
  login over as a portal user, so existing credentials keep working;
  `portal_email`/`portal_password` disappear from the client API.
- Self-hosted instances are single-agency by default: the first registration
  creates the owner agency and closes public sign-up (further attempts return
  403). Upgrading: instances that already have an agency stop accepting new
  public registrations; set `ALLOW_MULTI_AGENCY=true` to keep the previous
  multi-agency behavior.

### Fixed

- The inbox closes a conversation gracefully when it no longer exists (deleted
  by another operator or a cleanup) instead of erroring on click or polling the
  stale thread forever.
- The database engine now sends TCP keepalives and recycles pooled connections
  after 4 minutes, so a NAT or pooler between the API and a remote Postgres can
  no longer leave silently dropped connections hanging until the kernel timeout.
- The custom domain section on the client portal tab renders as a proper form
  row with styled status and DNS instructions; its CSS classes were never
  defined, so the icon, input and buttons stacked unstyled.

### Known issues

- Voice notes sent through the WhatsApp QR channel may not be downloadable by
  recipients due to a media upload issue in the pinned Baileys release
  (7.0.0-rc14). The WhatsApp Cloud API channel is unaffected.

## [0.3.0] - 2026-08-20

Upgrading: this release adds a database migration (applied automatically by the
Docker stack; run `alembic upgrade head` on local setups).

### Added

- WhatsApp Cloud API channel (official Meta API), independent from the QR
  channel: a client can have both connected on different numbers.
  - Bring your own Meta app: phone number ID, optional WABA id, permanent
    access token and app secret. Secrets are encrypted at rest and write-only
    (never returned by the API).
  - Per-channel webhook with the Meta verify handshake and HMAC-SHA256
    signature validation over the raw request body. The UI shows the callback
    URL and verify token with copy buttons and the Meta setup steps.
  - Inbound text, image and audio. Media is downloaded from the Graph API and
    goes through the same transcription/description pipeline as the QR
    channel; Meta webhook retries are deduplicated by message id.
  - AI replies and human operator replies (Inbox and client portal) are
    delivered through the Graph API.
  - "Connect and verify" validates the credentials against the Graph API and
    captures the number and verified name.
  - New "WhatsApp API" card on the Channels page and on the client channels
    tab, plus an inbox filter and badge for the new channel.
- `META_GRAPH_BASE_URL` setting (optional) to pin a Graph API version or point
  the channel at a mock server.

### Changed

- The Baileys channel is now labeled "WhatsApp QR" across the UI to
  distinguish it from the official API channel.
- The inbound WhatsApp pipeline (dedupe, conversation lookup, media handling,
  human takeover, AI reply) is shared between both channels.

## [0.2.0] - 2026-08-20

Upgrading: this release adds a database migration (applied automatically by the
Docker stack; run `alembic upgrade head` on local setups) and a new backend
dependency (`pip install -r requirements.txt`).

### Added

- Custom tools for agents, configured from a new Tools tab on the agent page:
  - HTTP tools: user-defined endpoint with `{param}` path placeholders, method,
    body and query parameters, prompt instructions, optional auth headers
    (encrypted at rest) and timeout.
  - MCP servers: external servers over SSE or Streamable HTTP with optional
    auth headers. The connection must be tested (tools listed) before saving,
    and the discovered tool list is cached so chat requests never block on
    discovery.
- Tool-calling loop for both providers (OpenAI Responses API and Anthropic
  Messages API), capped per reply, with token usage summed across iterations.
  Agents without tools are unaffected.
- Tool usage recorded on each assistant reply and shown in the playground,
  including the error detail when a call fails. When a tool fails, the agent
  reports the information as unavailable instead of answering from memory.
- SSRF guard for HTTP tools: URLs resolving to private, loopback or reserved
  addresses are rejected and redirects are never followed. Self-hosted
  deployments can opt out with `TOOLS_ALLOW_PRIVATE_URLS`.
- Unread count and last-message preview on inbox conversations.
- Channel badge on inbox conversations.

### Fixed

- Spacing of stacked provider cards in settings.

### Documentation

- Full documentation site at [openlivery.com/docs](https://openlivery.com/docs) with per-feature guides in English and Spanish.
- README restructured around the documentation site, with each feature linking to its guide.
- Corrected the WhatsApp inbound route in `CLAUDE.md`.

## [0.1.0] - 2026-08-16

First tagged release.

### Added

- Multi-tenant, agency-scoped data model: agencies, users, clients, agents,
  conversations and messages, with every query isolated by `agency_id`.
- FastAPI backend with JWT auth in httpOnly cookies, SQLAlchemy models and
  Alembic migrations.
- Next.js web app: auth, dashboard, clients, agents, inbox, chat playground,
  settings, client portal and an embeddable chat widget.
- Typed i18n system (English default, Spanish) for all user-facing copy.
- WhatsApp integration through a Baileys bridge, with stateful sessions and a
  human/AI conversation mode toggle.
- AI chat over any OpenAI-compatible endpoint, with per-connection base URL and
  model configuration and connection testing.
- Knowledge documents: PDF text extraction, chunking, embedding and semantic
  retrieval assembled into the agent system prompt.
- Structured business brief for agents.
- Encryption at rest for AI API keys and WhatsApp session state.
- OpenAI and Anthropic model presets, including the GPT-5.6 family
  (`gpt-5.6-sol`, `gpt-5.6-terra`, `gpt-5.6-luna`) and the `gpt-transcribe`
  transcription model.

### Infrastructure

- Docker Compose stack with a Makefile wrapper for build, run, migrate and test.
- Single-origin Caddy gateway (`/api/*` to the backend, everything else to the
  frontend).
- Prebuilt images published to GHCR.
- Per-IP rate limiting on public and unauthenticated endpoints.
- Custom per-client portal domains with on-demand TLS.
- README and self-hosting guide.

[Unreleased]: https://github.com/sarrazola/openlivery/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/sarrazola/openlivery/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/sarrazola/openlivery/releases/tag/v0.1.0
