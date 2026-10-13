# Push notifications

> Leer en español: [push-notifications.md](../es/push-notifications.md)

OpenLivery ships the notification *plumbing* and no notification *provider*.
There is no account to create, no third party involved, and nothing to pay for
in a default install: `PUSH_PROVIDER` is `none` and the server sends nothing.

This page explains what the plumbing does, what your options are for turning it
on, and the one constraint that surprises people.

## The constraint worth reading first

On iOS and Android the push credentials are bound to the **app binary**, not to
the server. Apple issues an APNs key to the developer account that publishes the
app; Google issues an FCM sender to the package name. A server can only notify
an app that was built against the provider that server sends through.

The practical consequence:

- **You run your own OpenLivery and use the official OpenLivery app from the
  store.** That app can read and answer everything on your server perfectly
  well, but it cannot receive push from it — the store build only accepts
  notifications from the credentials it was signed with, which belong to whoever
  published it. This is Apple's and Google's model, not a limitation we added.
- **You build the app yourself** under your own bundle identifier and push
  credentials — which the white-label setup already supports, see
  [`apps/mobile/WHITELABEL.md`](../../apps/mobile/WHITELABEL.md). Now push is
  entirely yours: you pick the provider, you hold the keys, you pay whoever you
  chose (or nobody).

So push is not something a self-hosted server is missing. It is something that
comes with building your own app, and this seam is what connects the two.

## How it works

Three pieces, all in the core:

1. **A device registry.** When someone signs in on a phone, the app registers
   with `POST /api/mobile/devices`, sending the token its provider issued.
   `GET /api/mobile/session` reports back `push.provider`, so an app pointed at
   a server with push off never initialises a push SDK at all — nothing
   subscribes, so nothing bills anyone.
2. **A dispatch point.** When a message arrives on a conversation an operator
   has taken over, the server notifies that client's registered devices. While
   the assistant is answering, nothing is sent: a phone that buzzes for every
   customer message is a phone whose notifications get switched off.
3. **A provider.** One function that takes a `Notification` and delivers it.

## Turning it on

### `none` (default)

Sends nothing. No configuration, no dependencies, no cost.

### `webhook`

Every notification is POSTed as JSON to a URL you control, and you route it from
there — ntfy, Gotify, Home Assistant, a Slack incoming hook, a queue, or a
five-line script that calls whatever service you already pay for.

```bash
PUSH_PROVIDER=webhook
PUSH_WEBHOOK_URL=https://example.com/openlivery-push
PUSH_WEBHOOK_SECRET=a-shared-secret   # optional; sent as a Bearer token
```

The body is stable:

```json
{
  "title": "Marta Ruiz",
  "body": "Hi, are you open on Saturday?",
  "data": { "conversation_id": "…", "client_id": "…" },
  "devices": [{ "token": "…", "platform": "ios" }]
}
```

### Your own provider

A provider is one async function. Register it at startup — from a wrapper module
that imports the app, so you never have to edit this repository:

```python
from app.services.notifications import Notification, register_provider

async def send_via_my_service(notification: Notification) -> int:
    ...  # deliver however you like
    return len(notification.devices)

register_provider("my-service", send_via_my_service)
```

Then set `PUSH_PROVIDER=my-service`. Registering an existing name replaces it,
so you can also override a built-in without a fork.

Device rows remember which provider issued their token, and tokens from a
provider you are no longer using are skipped rather than sent somewhere they
cannot arrive. After switching providers, apps re-register on their next launch.

## Browsers: the portal, no provider needed

Phones need a provider because their push credentials belong to whoever built
the app. Browsers do not: the Web Push protocol lets any server deliver to any
browser as long as the server signs with a key pair it owns (VAPID). So the
portal can ring with the portal closed and the browser open, on a self-hosted
install, with no account anywhere.

Turn it on by generating a key pair once and keeping it:

```bash
python -m app.webpush_keys
# PUSH_WEBPUSH_PRIVATE_KEY=...
```

Put the private key in `PUSH_WEBPUSH_PRIVATE_KEY` and, optionally, who the
browser vendors may contact about this sender in `PUSH_WEBPUSH_SUBJECT`
(`mailto:ops@example.com`). The public half is derived at runtime and handed to
the page. Do not rotate the key casually: every browser subscribed against the
old one has to subscribe again.

From then on each person has a **Browser notifications** switch under their
portal's Settings, Preferences. Turning it on asks the browser's permission,
registers the subscription for that person, and the server delivers directly
to the browser's push service (`apps/api/app/services/webpush.py`, RFC 8030,
8291 and 8292). Subscriptions sit in the same device registry as phones, under
the provider `webpush`, and go to the same people the phones do. A subscription
the push service reports gone (permission revoked, browser reset) is dropped on
the spot. While a portal window is visible, the page shows the message in place
instead of raising a system notification over it.

Web push is independent of `PUSH_PROVIDER`: a deployment can notify phones
through a provider and browsers directly, or browsers alone.

## Who gets notified

Notifications go to every device registered for the **client** the conversation
belongs to — so if a barbershop has three people answering, all three phones
ring, and whoever gets there first takes it. Devices are also linked to the
portal user who registered them, so removing someone from
`/clients/{id}/portal-users` stops their phone immediately.

## Failure behaviour

Delivery is best-effort on purpose. The message is already stored and will be
there when the app next opens, so a provider that is down, misconfigured or slow
never fails the request that produced it. Failures are logged and swallowed.
