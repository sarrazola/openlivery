# The mobile inbox

The inbox a client of an agency carries in their pocket. Sign in with the
address of the agency's server plus the portal credentials the agency handed
over, and the app shows that business's conversations, lets someone take over
from the assistant and reply — with photos, files and voice notes, like they
would from WhatsApp.

**This app carries no brand.** No name, no logo, no bundle identifier, no
preset pointing at anybody's hosted service. What is here is a working app and
the machinery to make it yours: put your identity in a brand file, build, and
publish it under your own name. See [WHITELABEL.md](./WHITELABEL.md).

It is also not part of the server install. Nobody running the platform needs to
build or deploy this to have it working — see [Effect on an existing
install](#effect-on-an-existing-install).

## What it does

- **Any server.** The address is typed at sign-in, so the same build works
  against a self-hosted instance or a hosted one. A build may add a preset for
  a service its publisher runs; none here has one.
- **The agency's colours.** Brand colour and logo arrive with the session and
  drive the interface, so the same binary looks like whichever agency the person
  belongs to.
- **Conversations and replies.** List, open, take over from the assistant,
  reply, hand back.
- **Attachments both ways.** Photos, videos, files and voice notes: what
  arrives renders in the conversation, and the composer can send the same.
- **Light and dark**, following the phone.
- **Notifications when the server can send them** — see
  [Notifications](#notifications).

## Running it locally

The app talks to a running server. Start one first (`make up` at the repo
root), then:

```bash
cd apps/mobile
npm install
BRAND=example npm run ios      # or: npm run android
```

`brands/example.json` is a placeholder identity for exactly this — running it
locally. It is not publishable, and it is not meant to be: copy it before you
build anything you intend to ship.

`BRAND` is required and has no default — see [WHITELABEL.md](./WHITELABEL.md)
for why.

On the iOS simulator `http://localhost:8000` reaches the server on your Mac. On
a physical phone, use the Mac's address on the network (`http://192.168.x.x:8000`)
and start the stack with `BIND_HOST=0.0.0.0` so it accepts connections beyond
loopback.

### Skipping the sign-in form while developing

Create `apps/mobile/.env.local` (git-ignored):

```
EXPO_PUBLIC_DEV_SERVER=http://localhost:8000
EXPO_PUBLIC_DEV_EMAIL=owner@thebusiness.com
EXPO_PUBLIC_DEV_PASSWORD=their-portal-password
```

With all three set the app signs in on launch. They are inlined at build time,
so a build you ship must not define them.

### Checking the flow end to end

Runs the same module the screens use against a real server: sign-in, branding,
a wrong password, resuming a token, listing, takeover, replying, handing back.

```bash
SERVER=http://localhost:8000 \
EMAIL=owner@thebusiness.com \
PASSWORD=their-portal-password \
npx tsx scripts/verify-flow.ts
```

## How it fits the server

Almost everything comes from the portal API the browser portal already uses.
Two things a phone cannot do the way a browser does, and what was added for
them, both in `apps/api/app/routers/mobile.py`:

| Problem | Endpoint |
| --- | --- |
| The portal is addressed by slug, which nobody types | `POST /api/mobile/sign-in` resolves the portal from the credentials |
| Sessions live in an httpOnly cookie, which native clients lose | The same token comes back in the body and is sent as `Authorization: Bearer` |

`_portal_client` in the portal router accepts that bearer token alongside the
cookie. Nothing else changed, and **there is no database migration**.

## Layout

```
apps/mobile/
  App.tsx                    three screens, no navigation library
  app.config.ts              builds the app identity from a brand file
  brands/                    one JSON per published app
  src/api.ts                 every call to the server
  src/session.ts             the stored token
  src/theme.ts               palette and brand-colour helpers
  src/screens/               sign-in, conversations, chat
  scripts/verify-flow.ts     end-to-end check against a server
```

## Notifications

The app asks the operating system for the native push token — APNs on iOS, FCM
on Android — and hands it to the server, which delivers through whatever it was
configured with. No push vendor's SDK is compiled in, on purpose: one build has
to work against a server that sends nothing and one that does, without either
borrowing the other's account.

So the server decides. `GET /api/mobile/session` reports `push.provider`, and
when it is `none` the app asks for no permission and registers nothing —
a prompt that leads to no notifications only teaches people to say no.

The part that surprises everyone: push credentials belong to the **app binary**,
not the server. A build can only be notified by a server sending through the
provider it was signed for. A build somebody else published can read
and answer everything on a self-hosted server, but cannot be notified by it. To
get push on your own server, publish your own build (see `WHITELABEL.md`) and
register a provider on the server side — the whole seam is documented in
[`docs/push-notifications.md`](../../docs/push-notifications.md).

## What is missing

Worth knowing before planning around it:

- **Attachments.** Conversations carrying images or voice notes show a
  placeholder; the server already stores and serves them. Sending them from the
  app is not built yet either.
- **Deep links from a notification.** The payload already carries
  `conversation_id`; opening straight into that conversation is not wired up.

## Effect on an existing install

Nothing changes for someone who upgrades and never touches the app. No new
service, no new required setting, and this directory is not installed with the
platform — it has its own `package.json`, the repo has no workspaces, and
nothing in `apps/api`, `apps/web` or `apps/whatsapp` imports from here.

On the server there is one migration, `0020`. It adds portal users and a device
registry, and copies each existing portal login into a user of its client, so
everyone keeps signing in with exactly the credentials they had. The old columns
stay and still authenticate. Notifications default to off and need no
configuration to stay that way.
