# Native Android inbox

A Kotlin and Jetpack Compose client for the portal inbox: the same screens as
`apps/ios`, built with Android's own frameworks only. It signs a client's
portal user in with `/api/mobile/sign-in`, keeps the bearer credential in a
file encrypted with a hardware-backed key, and calls the same portal API the
web and the iOS client use. The server enforces assignment, team access,
conversation status, reply windows and template rules; the app mirrors those
rules only to close its composer between polling ticks.

Requirements: Android Studio with the Android 15 SDK (API 36) or later, and
the JDK it bundles (the Gradle build targets 17 from any newer JDK).

```bash
cd apps/android
./gradlew :app:assembleDebug          # app/build/outputs/apk/debug/app-debug.apk
./gradlew :app:testDebugUnitTest      # the rules that do not need a server
./gradlew :app:installDebug           # onto the running emulator or a USB device
```

Open the `apps/android` directory in Android Studio to run it on a device or
an emulator. On the emulator, a server on the development machine is reached
at `10.0.2.2`, which the app accepts over plain HTTP like any local address.

## Layout

| Path | Purpose |
| --- | --- |
| `brand/brand.properties` | The identity this build compiles with (see `WHITELABEL.md`) |
| `brand/res` | Launcher icon, sign-in logo and icon background, beside the brand file |
| `app/build.gradle.kts` | Reads the brand file into the application id, version and `BuildConfig` |
| `app/src/main/kotlin/.../api` | Models and the portal client; one function per route |
| `app/src/main/kotlin/.../storage` | Encrypted session and privacy consent |
| `app/src/main/kotlin/.../rules` | Reply windows, channel capabilities, names, dates |
| `app/src/main/kotlin/.../localization` | English and Spanish copy, chosen by the phone's language |
| `app/src/main/kotlin/.../ui` | Sign-in, privacy, inbox, thread, contacts, settings |
| `app/src/test` | Unit tests for the rules that do not need a server |

## Behaviour worth knowing

- The server address is typed at sign-in, or derived from a workspace name when
  the brand carries a hosted preset. Plain HTTP is accepted only for local
  network addresses (`localhost`, `10.x`, `192.168.x`, `172.16-31.x`, and the
  emulator's `10.0.2.2`), which is what `network_security_config.xml` allows.
- The privacy screen is shown until the person accepts the disclosure the server
  returns; the acceptance is stored as a fingerprint of that disclosure, so a
  new destination or version asks again.
- Returning from the background re-checks the session with the server while a
  consented session stays on screen.
