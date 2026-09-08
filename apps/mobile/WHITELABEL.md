# Publishing a branded build

This application is a separate Expo package. A publisher supplies its identity,
assets, server and signing credentials. No hosted service or delivery account is
required by the source itself.

## Identity and assets

Copy `brands/example.json` to `brands/youragency.json` and replace its values:

```json
{
  "name": "Your Agency Inbox",
  "slug": "your-agency-inbox",
  "scheme": "youragencyinbox",
  "iosBundleIdentifier": "com.youragency.inbox",
  "androidPackage": "com.youragency.inbox",
  "primaryColor": "#1f6feb",
  "defaultServer": "https://chat.youragency.com",
  "version": "0.2.0"
}
```

Replace the icon, adaptive icon and splash images in `assets/`. The sign-in screen
uses the compiled icon and app name. Once authenticated, the client's current
branding is loaded from the server.

A publisher operating multiple workspaces may add a preset:

```json
"hosted": {
  "label": "Your Service",
  "serverTemplate": "https://{workspace}.yourdomain.com"
}
```

The screen offers this preset alongside a custom server address. Workspace names
are validated as a single DNS label before building the address. Omit custom
workspace labels to keep the built-in English and Spanish UI translations.

Optional brand fields:

| Field | Purpose |
| --- | --- |
| `version` | User-facing application version |
| `iosBuildNumber`, `androidVersionCode` | Initial local native build versions |
| `iosAppleTeamId` | Xcode team; `APPLE_TEAM_ID` can supply it instead |
| `owner`, `easProjectId` | Existing EAS account/project association |
| `androidGoogleServicesFile` | Local Firebase application config path |
| `nativePlugins` | Optional Expo config-plugin paths for publisher-specific native integration |

Use identifiers and assets you are entitled to publish. Store approval depends
on the final application and publisher's submission; a brand file alone does not
establish eligibility. Consult the current [Apple review guidelines](https://developer.apple.com/app-store/review/guidelines/)
and [Google Play publication requirements](https://support.google.com/googleplay/android-developer/answer/9859348)
for the account and distribution path being used.

## Build profiles

Install with `npm ci`. `eas.json` includes development, simulator, preview and
production profiles. Set `build.<profile>.env.BRAND` to your brand in every
profile you use. The example development profile selects the placeholder brand;
preview and production deliberately have no publisher identity selected.

EAS evaluates config both locally and on its builder. Exporting `BRAND` only in
your terminal is insufficient: save the brand in the profile or its selected EAS
environment. See [EAS build profiles](https://docs.expo.dev/build/eas-json/).

```bash
BRAND=youragency APP_VARIANT=development npx expo run:ios
BRAND=youragency APP_VARIANT=development npx expo run:android
BRAND=youragency npx eas-cli build --platform all --profile production
```

The production profile increments native build versions using EAS remote version
management. A successful build is an artifact; it does not submit or publish it.
There is no automatic submission configured.

`.easignore` excludes generated native projects so EAS regenerates them from
`app.config.ts`. Keep native settings in that config, brand fields or plugins.
After adding a native dependency or changing plugins locally, regenerate the
native projects and rebuild. Preserve manual signing changes before using
`expo prebuild --clean`.

Release config rejects embedded `EXPO_PUBLIC_DEV_*` credentials. Store builds use
HTTPS; `APP_VARIANT=development` explicitly allows HTTP for disposable local
backends. Never set that variant on a store profile. Browser preview sessions
are memory-only; native sessions are held in the platform credential store.

## Optional notifications

The binary registers native APNs/FCM tokens with its authenticated server. The
server must be able to deliver to the same application identifiers. No vendor
SDK or notification-service account is shared by this source.

For Android, supply the Firebase application configuration for the package being
built. `GOOGLE_SERVICES_JSON` can be a local path or an EAS file environment
variable; it takes precedence over `androidGoogleServicesFile`. The server's
FCM credentials must belong to that Firebase project. For iOS, configure the
signing capabilities and matching APNs delivery credentials for the bundle ID.
Native APNs/FCM delivery is separate from the optional Expo Push Service.

See [Expo notification configuration](https://docs.expo.dev/versions/latest/sdk/notifications/)
and the repository's [push provider documentation](../../docs/push-notifications.md).
Do not commit signing keys or service credentials. If notifications are disabled
on the server, the application asks for no push permission.

## Release verification

Before distributing a candidate, run the package's typecheck and native contract
tests, validate the native config, then test signed builds on both platforms
against the API revision being released. Exercise session restoration, inbox
filters, permissions, takeover/assignment, text and attachments, reconnecting,
and notification navigation. Verify actual push delivery on a physical device.

Provide reviewers with a working account, reachable backend and representative
conversations. Supply current screenshots, support/privacy links and the data
handling declarations for the actual deployment. Complete any testing or signing
requirements shown by the publisher's store account.

Over-the-air updates are not configured by this package. Adding that capability
requires a separate `expo-updates`/EAS Update setup and a native runtime policy;
until then, distribute changes through new native builds.
