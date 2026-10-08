# Native iOS inbox

A SwiftUI client for the portal inbox: the same screens as `apps/mobile`, built
with Apple's frameworks only. It signs a client's portal user in with
`/api/mobile/sign-in`, keeps the bearer credential in the Keychain, and calls the
same portal API the web and the Expo client use. The server enforces assignment,
team access, conversation status, reply windows and template rules; the app
mirrors those rules only to close its composer between polling ticks.

Requirements: Xcode 16 or later, iOS 17 or later, and
[XcodeGen](https://github.com/yonaskolb/XcodeGen) (`brew install xcodegen`).

```bash
cd apps/ios
xcodegen generate        # writes Inbox.xcodeproj, which is never committed
open Inbox.xcodeproj     # pick a simulator and run
```

From the command line:

```bash
xcodebuild -project Inbox.xcodeproj -scheme Inbox \
  -destination 'platform=iOS Simulator,name=iPhone 17' CODE_SIGNING_ALLOWED=NO build
xcodebuild -project Inbox.xcodeproj -scheme Inbox \
  -destination 'platform=iOS Simulator,name=iPhone 17' CODE_SIGNING_ALLOWED=NO test
```

## Layout

| Path | Purpose |
| --- | --- |
| `project.yml` | XcodeGen specification; identity settings reference `$(BRAND_*)` variables |
| `Brand/Brand.xcconfig` | The identity this build compiles with (see `WHITELABEL.md`) |
| `Inbox/Info.plist` | Reads the brand variables into a `Brand` dictionary the app loads at launch |
| `Inbox/Sources/API` | Models and the portal client; one function per route |
| `Inbox/Sources/Storage` | Keychain-backed session and privacy consent |
| `Inbox/Sources/Rules` | Reply windows, channel capabilities, names, notification routing |
| `Inbox/Sources/Localization` | English and Spanish copy, chosen by the phone's language |
| `Inbox/Sources/Media` | Attachment cache, voice note recorder and player |
| `Inbox/Sources/Push` | APNs registration, driven by what the server says it can send |
| `Inbox/Sources/Views` | Sign-in, privacy, inbox, thread, contacts, workspace |
| `InboxTests` | Unit tests for the rules that do not need a server |

## Behaviour worth knowing

- The server address is typed at sign-in, or derived from a workspace name when
  the brand carries a hosted preset. Plain HTTP is accepted only for local
  network addresses (`localhost`, `10.x`, `192.168.x`, `172.16-31.x`), which is
  what `NSAllowsLocalNetworking` in Info.plist allows.
- Notifications are requested only when the session says the server can send
  them. The APNs token is handed to the server; no vendor SDK is involved. A
  publisher whose delivery service wraps the payload replaces
  `Rules/NotificationData.swift` in their build.
- The privacy screen is shown until the person accepts the disclosure the server
  returns; the acceptance is stored as a fingerprint of that disclosure, so a
  new destination or version asks again.
- Drafts live in memory for the session and are cleared on sign-out.
