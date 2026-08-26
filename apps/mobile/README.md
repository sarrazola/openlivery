# OpenLivery mobile

The inbox a client of an agency carries in their pocket. Sign in with the
address of the agency's server plus the portal credentials the agency handed
over, and the app shows that business's conversations, lets someone take over
from the assistant and reply.

It is not part of the server install. Nobody running OpenLivery needs to build
or deploy this to have a working platform — see [Effect on an existing
install](#effect-on-an-existing-install).

## What it does

- **Any server.** The address is typed at sign-in, so the same build works
  against a self-hosted instance or a hosted one.
- **The agency's colours.** Brand colour and logo arrive with the session and
  drive the interface, so the same binary looks like whichever agency the person
  belongs to.
- **Conversations and replies.** List, open, take over from the assistant, reply,
  hand back.

Not here yet: push notifications, attachments and voice notes. See
[What is missing](#what-is-missing).

## Running it locally

The app talks to a running OpenLivery server. Start one first (`make up` at the
repo root), then:

```bash
cd apps/mobile
npm install
BRAND=openlivery npm run ios      # or: npm run android
```

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

## What is missing

Worth knowing before planning around it:

- **Push notifications.** The reason to have an app at all is that a phone
  rings when the assistant escalates. That needs a device-token table, per-agency
  APNs/FCM credentials and a dispatch path on inbound messages. Until then the
  app polls while it is open — 15s on the list, 10s in a conversation.
- **One login per business.** A portal has a single e-mail and password, shared
  by everyone at the business. That is survivable in a browser and a problem
  with push, where you have to know which phone to ring and who replied. A real
  `PortalUser` is the prerequisite, and it is cheaper to do before devices are
  registered than after.
- **Attachments.** Conversations carrying images or voice notes show a
  placeholder; the server already stores and serves them.

## Effect on an existing install

None. This directory has its own `package.json`, the repo has no workspaces, and
nothing in `apps/api`, `apps/web` or `apps/whatsapp` imports from here. Someone
cloning the repo to run the platform never installs it.

The server side is two additions and one widened check: a new router, its
registration, and portal auth accepting a bearer token in addition to the cookie
it already accepted. No schema change, no new environment variable, no new
service. An install that upgrades and never touches the app behaves exactly as
before.
