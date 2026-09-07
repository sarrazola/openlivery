# The mobile inbox

A native Expo application for the client portal. It uses the same portal API,
permissions and conversation state as the browser inbox. The server remains the
source of truth for assignment, assistant takeover, routing, replies and access.

The source contains a placeholder identity for development. Publishers supply a
brand file and their own assets; see [WHITELABEL.md](./WHITELABEL.md). Installing
or upgrading the server does not require building this application.

## Inbox behavior

- Search and filter WhatsApp, Instagram, Facebook Messenger and web conversations by channel and inbox state. Social replies follow the server's response windows and attachment capabilities.
- Open the complete conversation, with the contact and assistant context.
- Take over a conversation, reply, and return it to an assistant.
- Render incoming attachments and send photos, videos, documents and voice notes.
- Use the phone's light/dark appearance and English/Spanish locale.
- Resume a portal session with credentials held in Keychain/Android Keystore.
- Register native notification tokens when the server supports delivery, and open
  the referenced conversation when a notification is tapped.

Native notifications require a physical device and matching delivery credentials.
An app running on a simulator can exercise the inbox without them. Polling pauses
when the app goes into the background and refreshes when it becomes active again.
A temporary network failure does not invalidate a stored login.

## Local development

Start a disposable backend following the repository's development instructions,
then run:

```bash
cd apps/mobile
npm ci
BRAND=example APP_VARIANT=development npx expo run:ios
# Or, with an Android emulator already running:
BRAND=example APP_VARIANT=development npx expo run:android
```

The app includes native modules, so use its development build rather than relying
on Expo Go for verification. After the native application has been built, start
Metro with `BRAND=example APP_VARIANT=development npx expo start --dev-client`.

The iOS simulator reaches a Mac backend at `http://localhost:8000`. Android's
emulator uses `http://10.0.2.2:8000`. Physical phones need the Mac's LAN address
and a backend listening on that network interface.

HTTP is enabled only for development variants. Release variants require HTTPS.
The native network policy is compiled into the application, so changing
`APP_VARIANT`, permissions, plugins or native dependencies requires rebuilding.

### Optional development sign-in

A git-ignored `.env.local` can prefill a disposable local account:

```dotenv
EXPO_PUBLIC_DEV_SERVER=http://localhost:8000
EXPO_PUBLIC_DEV_EMAIL=owner@example.test
EXPO_PUBLIC_DEV_PASSWORD=local-fixture-password
```

Automatic sign-in runs only in a development JavaScript bundle. Release config
also refuses any nonempty `EXPO_PUBLIC_DEV_*` variable, and the EAS archive
excludes `.env*`. Use fixture credentials only; never use a production account
for automatic sign-in.

### Validation

```bash
npm run typecheck
npm run test:native-contracts
BRAND=example npx expo install --check
BRAND=example APP_VARIANT=production npx expo config --type introspect
```

`test:native-contracts` exercises encrypted-session migration, sign-out,
release credential guards and push registration behavior with mocked native
adapters. It does not establish that a phone received an APNs/FCM notification.

A real-server script exercises the API module used by the screens:

```bash
SERVER=http://localhost:8000 \
EMAIL=owner@example.test \
PASSWORD=local-fixture-password \
npx tsx scripts/verify-flow.ts
```

Use only a disposable development account: this script changes conversation
state and sends a test reply. Record native runtime checks separately from API
checks and JavaScript compilation.

## Session and notification boundaries

`POST /api/mobile/sign-in` accepts portal-user credentials and resolves the
client without requiring a portal slug. `GET /api/mobile/session` validates the
bearer session and returns current branding and push capability.
Other inbox calls use the portal routes with that bearer token.

Only the server address and token are persisted. Existing AsyncStorage sessions
are migrated into encrypted storage, then removed from plaintext storage. Browser
previews keep their token in memory. Branding and permissions are refreshed from
the backend rather than persisted with the credential.

Push delivery is provider-neutral in the application. It registers an APNs token
on iOS or an FCM token on Android, and the configured server provider delivers to
it. Android creates the messages notification channel before asking permission.
Rotated device tokens are registered again. Signing out releases the registered
device, and notification navigation still fetches the conversation through the
current authenticated session.

## Source layout

| File | Responsibility |
| --- | --- |
| `App.tsx` | Session lifecycle, screen stack and notification navigation |
| `app.config.ts` | Brand identity, native plugins and release guards |
| `eas.json` | Development, simulator, preview and production profiles |
| `plugins/withNetworkPolicy.js` | Native HTTP policy per build variant |
| `src/api.ts` | Typed portal/mobile API and attachment requests |
| `src/session.ts` | Secure persistence and legacy migration |
| `src/push.ts` | Optional native token registration |
| `src/i18n.ts` | Typed English and Spanish strings |
| `src/screens/` | Sign-in, inbox and conversation screens |
| `src/components/` | Composer and attachment UI |

The app is a separate package: it is not installed by the API, web or bridge
packages. Its API dependencies still have to exist on the server before a new
binary can be distributed; test the app against the server revision being
released.
