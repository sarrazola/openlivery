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
