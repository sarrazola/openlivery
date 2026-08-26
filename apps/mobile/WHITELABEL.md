# Publishing your own build

An agency can publish this app under its own name, with its own icon, pointing
at its own server. This page is the checklist.

The short version: copy a JSON file, build with `BRAND=` set, publish from your
own developer account.

## Why you publish it, and not us

Apple's guideline 4.2.6 covers apps built from a template or an app-generation
service. It draws one line: **the owner of the content submits the app, not the
provider of the template.** So we do not publish on your behalf. You download
the source, build it with your brand, and submit from your own account. That is
the compliant side of the line, and it is what Rocket.Chat, Mattermost,
Nextcloud and Moodle forks already do.

The same guideline has a second half that matters more than people expect: the
apps must be genuinely distinct. An app that is another app with a different
logo gets rejected — under 4.2.6 for still being a template app, or under 4.3
as a duplicate. The licence of the source is irrelevant to that judgement.

**What makes yours distinct, in the order reviewers notice:**

| Signal | What to do |
| --- | --- |
| The server it talks to | Point it at your own domain, not someone else's |
| Screenshots | Your own, with your data |
| Store description | Write it yourself; do not paste a template |
| Bundle identifier | Your own reverse-domain, e.g. `com.youragency.inbox` |
| Name and icon | Yours |

If your clients are a known list rather than the public, look at **unlisted
distribution** on the App Store: the app installs from a direct link and does
not appear in search. Less duplicate scrutiny, and a better fit for "this is for
my clients", which is usually the truth.

## 1. Your brand file

```bash
cp brands/example.json brands/youragency.json
```

Every field must be yours:

```json
{
  "name": "Your Agency Inbox",
  "slug": "your-agency-inbox",
  "scheme": "youragencyinbox",
  "iosBundleIdentifier": "com.youragency.inbox",
  "androidPackage": "com.youragency.inbox",
  "primaryColor": "#1f6feb",
  "defaultServer": "https://chat.youragency.com"
}
```

`defaultServer` pre-fills the sign-in field so your clients do not type an
address. `primaryColor` only paints the sign-in screen — after signing in, the
colour comes from your agency record on the server, so changing it there changes
every installed app without a resubmission.

If you run a service several agencies sign in to, add a `hosted` block and the
sign-in screen offers it as a choice — someone names their workspace and the
address is derived — with "Another server" alongside for anyone pointing
elsewhere. `brands/_hosted-example.json` shows the shape:

```json
"hosted": {
  "label": "Your Cloud",
  "serverTemplate": "https://{workspace}.yourdomain.com"
}
```

Only two fields, because the rest is interface copy the app already translates.
If "agency" is the wrong word for your customers, `workspaceLabel` and
`workspacePlaceholder` override it — in one language, so leave them out unless
you need them.

Replace the icons in `assets/` with yours — the ones here are a plain
placeholder, not a brand. Shipping somebody else's mark under
your name is both a rejection risk and a trademark problem.

## 2. Build

```bash
BRAND=youragency npx expo run:ios      # local check
BRAND=youragency eas build --platform all --profile production
```

There is no default brand on purpose: a build without `BRAND` fails instead of
quietly producing something identical to another agency's app.

## 3. Notifications (optional)

Push credentials belong to the build, so they are yours to set up and yours to
pay for — which is also why a build of this app can never be notified through
anybody else's account.

Two halves have to agree:

- **The build.** `eas credentials` uploads your APNs key (iOS) and FCM service
  account (Android). Nothing else in this directory changes; the app already
  asks the OS for a native token.
- **The server.** Set `PUSH_PROVIDER` to a provider your server has
  registered. `webhook` ships with it and needs no account anywhere — point it
  at whatever you already use. Writing your own provider is about twenty lines;
  see [`docs/push-notifications.md`](../../docs/push-notifications.md).

Skip this entirely and the app still works: it polls while open, and asks for no
notification permission at all.

## 4. Before you submit

The ones that cause most rejections, in order:

- **A working demo account.** Apple's 2.1 requires reviewers to be able to sign
  in. Give them a real portal login on your server with a conversation or two in
  it. Forgetting this is an automatic rejection, not a maybe.
- **Privacy details.** The app sends the e-mail, password and messages the user
  types to the server *you* run. Declare that, and give a privacy policy URL
  and a support URL of your own.
- **An organisation account** if the app should appear under your company's name
  rather than a person's. Apple requires a D-U-N-S number for that, which can
  take weeks — start before you need it.
- **Google Play closed testing.** New personal accounts must run a closed test
  with 12 testers for 14 days before production. Organisation accounts are
  exempt.

Costs: $99/year Apple, $25 once for Google.

## 5. Keeping it updated

Most changes here are JavaScript, which `eas update` can ship over the air
without another review. Only changes to native code or app configuration need a
new build and a resubmission. Set up an EAS project per brand so your updates go
to your users and nobody else's.

## Naming

The MIT licence covers the code. It does not cover anybody's name or logo,
including this project's — which is why nothing in this directory carries one.
Publish under your own name and icon.
