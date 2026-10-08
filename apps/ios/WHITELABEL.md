# Publishing a branded iOS build

The app compiles with whatever identity `Brand/Brand.xcconfig` carries. A
publisher supplies that file, the icon set and signing. Nothing in the source
points at a hosted service.

## Identity

Replace every value in `Brand/Brand.xcconfig`:

```
BRAND_PRODUCT_NAME = Your Agency Inbox
BRAND_BUNDLE_IDENTIFIER = com.youragency.inbox
BRAND_URL_SCHEME = youragencyinbox
MARKETING_VERSION = 1.0.0
CURRENT_PROJECT_VERSION = 1
DEVELOPMENT_TEAM = ABCDE12345
BRAND_PRIMARY_COLOR = 1f6feb
BRAND_DEFAULT_SERVER = chat.youragency.com
```

Addresses are written without a scheme because `//` starts a comment in an
xcconfig file. The app prepends `https://` to every one of them. The colour is
six hex digits with no `#`; it only paints the sign-in screen, since the
workspace's own colour arrives with the session.

A publisher that runs a hosted service may add a preset. The sign-in screen then
offers it alongside typing an address, and a workspace name is enough:

```
BRAND_HOSTED_LABEL = Your Service
BRAND_HOSTED_SERVER_TEMPLATE = {workspace}.yourdomain.com
```

A hosted service may also run a directory so its people sign in with an e-mail
alone. The app POSTs `{"email", "password"}` to it and expects
`{"accounts": [{"server": "https://...", "session": <the sign-in response>}]}`:
one account signs in straight away, several let the person choose. Without it
the hosted option asks for the workspace name.

```
BRAND_HOSTED_SIGN_IN = yourdomain.com/api/directory/sign-in
```

Privacy policy and support links appear on the sign-in and privacy screens when
set, in the phone's language with English as the fallback:

```
BRAND_PRIVACY_POLICY_URL_EN = yourdomain.com/privacy
BRAND_PRIVACY_POLICY_URL_ES = yourdomain.com/es/privacidad
BRAND_SUPPORT_URL_EN = yourdomain.com/support
```

## Assets

Replace `Inbox/Assets.xcassets/AppIcon.appiconset/AppIcon.png` (1024 x 1024, no
transparency for the store), the launch image in `LaunchIcon.imageset` and the
`AccentColor` colour set.

## Keeping the source untouched

The intended way to brand is to copy `apps/ios` somewhere, overwrite the brand
file and the assets, then `xcodegen generate` there. Nothing in `project.yml`
or `Inbox/Sources` needs editing, which keeps your copy trivially upgradable
when the source moves. If your notification service wraps the payload, overwrite
`Inbox/Sources/Rules/NotificationData.swift` with an adapter for its envelope;
the rest of the app only reads the flat dictionary it returns.

## Signing and release

Automatic signing with the team in `DEVELOPMENT_TEAM`. Archive with Xcode or:

```bash
xcodebuild -project Inbox.xcodeproj -scheme Inbox -configuration Release \
  -destination 'generic/platform=iOS' -archivePath build/Inbox.xcarchive archive
```

Release builds use the `production` APNs environment and Debug builds use
`development`, both from the entitlements the project generates. Test against the
API revision that will serve the app before submitting.
