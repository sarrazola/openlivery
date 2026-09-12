# Client portal & domains

> Leer en español: [client-portal.md](../es/client-portal.md)

Each client gets its own portal: a separate login and a focused inbox where they can read conversations and take over from the AI, without ever seeing your agency dashboard. Optionally, you can serve that portal on the client's own custom domain with automatic HTTPS.

## The client portal

The portal is a self-contained space scoped to a single client. It has its own login (separate from your agency account) and shows only that client's agents and conversations — the same inbox your operators use, but limited to one client. From there the client can switch a conversation to `human` mode to pause the AI and reply themselves.

The portal is disabled by default. You enable it per client from the client's settings, and it becomes reachable only once a login email and password are set.

## Portal settings

On a client you configure these fields:

- **`portal_enabled`** — the toggle that turns the portal on. It cannot be enabled until a `portal_email` and a password are set.
- **`portal_slug`** — the URL segment for the portal (e.g. `acme` → `/portal/acme`). It is generated from the client name on creation, must be unique, and is normalized to a slug when you change it.
- **`portal_title`** — the heading shown on the portal login and inbox. If left empty it falls back to `"<Client name> Inbox"`.
- **`portal_email`** — the address the client signs in with.
- **`portal_password`** — the client's password (minimum 8 characters). It is stored hashed; the API only reports whether one is configured, never the value.

Enabling the portal without both an email and a password is rejected.

## People and roles

The people who sign in to a portal are managed by the agency from the client's **Portal** tab (`/api/clients/{id}/portal-users`). Each person has a role:

- **Admin** can do everything in the portal.
- **Agent** works the inbox: reads and answers, takes a conversation from the AI and hands it back, changes its status, assigns it to a person or a team, creates contacts and puts existing tags on them, and sets their own availability. An agent cannot delete or archive conversations, import, export, delete, merge or block contacts, manage tags, WhatsApp templates, saved replies or teams, or open the reports.

The first person added to a business is its admin; everyone added after starts as an agent until the agency changes it. The API guards every route by permission key (`app/portal_permissions.py`), so the mobile app is covered by the same rule, and the portal session (`GET /api/portal/{slug}/me`) lists the permissions the person holds so the UI can hide what they cannot do.

## Teams and templates from the agency

Teams and WhatsApp templates belong to the client and can be managed from either side: the client's portal, or the agency's client page under its **Teams** and **WhatsApp templates** tabs (`/api/clients/{id}/teams`, `/api/clients/{id}/templates`). Both doors edit the same rows.

## Portal URL

Every enabled portal is served at:

```
/portal/<slug>
```

For example, a client with slug `acme` on a stack at `https://app.example.com` reaches its portal at `https://app.example.com/portal/acme`. The portal login, inbox and conversation views all live under this path.

## Custom per-client domain (optional)

Instead of the shared `/portal/<slug>` path, you can point the portal at a domain the client owns, such as `support.acme.com`, with a certificate issued automatically.

### Add a custom domain

1. In the client's settings, set the custom domain (e.g. `support.acme.com`). Saving it resets verification and issues a fresh challenge token.
2. Create a DNS **TXT** record at `_openlivery-challenge.<domain>` with the token value shown in the settings.
3. Click **Verify**. OpenLivery resolves the TXT record; once it matches the token, the domain is marked verified.
4. Point the domain itself at your server (an A/AAAA or CNAME record for `support.acme.com`).
5. Make sure the on-demand TLS gateway is enabled (see below) — the certificate is then obtained automatically on the first request.

### How it works

- The public, unauthenticated endpoint `GET /api/public/portal-domain?domain=<host>` maps a host to its portal. It returns `{ "portal_slug": ... }` only when the domain matches a client that is verified and enabled, and a non-2xx otherwise.
- The Next.js `proxy.ts` resolves the incoming host against that endpoint and rewrites a verified host to `/portal/<slug>`, so the browser URL stays on the client's own domain. It reaches the API server-side through `BACKEND_INTERNAL_URL` — see [Configuration](configuration.md).
- `docker/Caddyfile.ondemand` gates on-demand TLS with the same endpoint as its `ask` hook, so a certificate is issued only for verified portal domains and never for arbitrary hosts pointed at the server.

The on-demand gateway is opt-in. See [Self-hosting](self-hosting.md) for mounting the override and publishing ports 80 and 443.

## Archiving and deleting conversations

Conversations are the client's history, so nothing removes them in one step.

- **Archive** a resolved conversation from its header, or every resolved conversation at once from the Resolved inbox. Archived conversations leave the inboxes, keep every message, still count in reports, and can be restored (they come back as resolved). Archiving an open conversation resolves it first.
- **Delete** only from the Archived inbox, one at a time or all of them, after typing the confirmation word. Deleting removes the conversation and its messages from the database for good.

Deleting an agent from the dashboard never touches conversations: they stay in the portal under the agent's name. Deleting a client does remove them, together with everything else under the client.

API: `GET /api/portal/{slug}/conversations?archived=1`, `PATCH .../conversations/{id}/archive` with `{"archived": true|false}`, `POST .../conversations/archive-resolved`, `DELETE .../conversations/{id}` (archived only), `POST .../conversations/delete-archived`. The inbox summary carries an `archived` count.

## Blocking a contact

A contact that spams the number can be **blocked** from Contacts or from the conversation header. Blocked, their messages are still stored but nobody answers them: the agent does not reply and spends no tokens, no notification fires, and their conversations leave every inbox (they stay readable from the contact's history). They can keep writing; they just get no response.

**Unblocking** does not answer the backlog. The open conversation is resolved with a note in the thread, and the contact's next message opens a fresh conversation that the agent handles as usual.

API: `POST /api/portal/{slug}/contacts/{id}/block` with `{"blocked": true|false}`; `ContactOut.blocked_at` says whether a contact is blocked. This is an internal block: WhatsApp itself is not told, so the contact sees their messages as delivered.
