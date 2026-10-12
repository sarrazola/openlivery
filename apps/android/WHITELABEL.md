# Publishing a branded Android build

The app compiles with whatever identity `brand/brand.properties` carries and
whatever `brand/res` holds. A publisher supplies that directory and signing.
Nothing in the source points at a hosted service.

## Identity

Replace every value in `brand/brand.properties`:

```
BRAND_PRODUCT_NAME=Your Agency Inbox
BRAND_APPLICATION_ID=com.youragency.inbox
BRAND_URL_SCHEME=youragencyinbox
MARKETING_VERSION=1.0.0
CURRENT_PROJECT_VERSION=1
BRAND_PRIMARY_COLOR=1f6feb
BRAND_DEFAULT_SERVER=chat.youragency.com
```

Addresses are written without a scheme; the app prepends `https://` to every
one of them. The colour is six hex digits with no `#`; it only paints the
sign-in screen, since the workspace's own colour arrives with the session.

A publisher that runs a hosted service may add a preset, and a directory so
its people sign in with an e-mail alone, exactly as on iOS:

```
BRAND_HOSTED_LABEL=Your Service
BRAND_HOSTED_SERVER_TEMPLATE={workspace}.yourdomain.com
BRAND_HOSTED_SIGN_IN=yourdomain.com/api/directory/sign-in
BRAND_PRIVACY_POLICY_URL_EN=yourdomain.com/privacy
BRAND_PRIVACY_POLICY_URL_ES=yourdomain.com/es/privacidad
BRAND_SUPPORT_URL_EN=yourdomain.com/support
```

## Assets

Replace the files under `brand/res`: the adaptive launcher icon
(`mipmap-anydpi-v26/ic_launcher.xml` with its foreground drawable and the
`launcher_background` colour) and `drawable/brand_logo` shown on the sign-in
screen. Bitmaps go in `drawable-nodpi` or the density folders; the names must
stay the same.

## Keeping the source untouched

Copy `apps/android` somewhere, replace the `brand` directory, then build there.
Nothing in `app/` needs editing, which keeps your copy trivially upgradable
when the source moves. If your notification service wraps the payload, add its
adapter in your copy; the rest of the app only reads a flat map of data.

## Signing and release

Store builds are App Bundles signed with your upload key:

```bash
./gradlew :app:bundleRelease   # app/build/outputs/bundle/release/app-release.aab
```

Provide the upload keystore outside the repository, as Gradle properties
(`uploadKey.STORE_FILE`, `uploadKey.STORE_PASSWORD`, `uploadKey.KEY_ALIAS`,
`uploadKey.KEY_PASSWORD` in `~/.gradle/gradle.properties`) or as the
environment variables `UPLOAD_KEY_STORE_FILE`, `UPLOAD_KEY_STORE_PASSWORD`,
`UPLOAD_KEY_KEY_ALIAS` and `UPLOAD_KEY_KEY_PASSWORD`. With them absent the
release bundle is built unsigned. Never put the keystore in the source tree.
