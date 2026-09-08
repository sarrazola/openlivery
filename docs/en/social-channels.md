# Instagram and Facebook Messenger

OpenLivery can receive direct messages for Instagram professional accounts and
Facebook Pages, answer through an agent or a human operator, and show these
conversations alongside other channels in the client inbox. A personal Facebook
profile inbox and Instagram group messages are not supported.

This integration requires an operator-created Meta application and the access
level appropriate to the accounts it serves. Installing the software does not
approve an application or grant permissions. Complete the live-account checks
below before enabling an unattended agent.

## Application setup

Serve the frontend and API at a public HTTPS origin. Apply the database migration
before starting the updated API and web application. Keep `ENCRYPTION_KEY`
stable: tokens and application secrets are encrypted with it.

Set the following environment variables on the API server. Never put application
secrets or tokens in `NEXT_PUBLIC_*` variables, browser storage, screenshots, or
source control.

| Variable | Purpose |
| --- | --- |
| `SOCIAL_PUBLIC_URL` | Public HTTPS origin for callbacks and webhooks; defaults to `FRONTEND_URL`. |
| `FRONTEND_URL` | HTTPS origin used for safe browser return navigation. |
| `SOCIAL_GRAPH_VERSION` | Supported Graph API version, default `v25.0`; change only after testing. |
| `INSTAGRAM_APP_ID` | Instagram App ID from Instagram product settings. |
| `INSTAGRAM_APP_SECRET` | Matching Instagram App Secret. |
| `INSTAGRAM_WEBHOOK_VERIFY_TOKEN` | Random secret used to verify the configured webhook callback. |
| `INSTAGRAM_HUMAN_AGENT_ENABLED` | Enable only after Human Agent approval for this application. |
| `MESSENGER_HUMAN_AGENT_ENABLED` | Enable only after Human Agent approval for this application. |
| `MESSENGER_APP_ID` | Application ID for Facebook Login and Messenger. |
| `MESSENGER_APP_SECRET` | Matching application secret. |
| `MESSENGER_WEBHOOK_VERIFY_TOKEN` | Random webhook verification secret. |
| `MESSENGER_LOGIN_CONFIG_ID` | Optional Facebook Login for Business configuration ID. |
| `SOCIAL_WORKER_ENABLED` | Enables durable event processing and token maintenance; default `true`. |
| `SOCIAL_WORKER_INTERVAL_SECONDS` | Worker polling interval; default `2`. |

### Instagram

Use **Instagram API with Instagram Login**. The receiving account must be a
professional business or creator account. A linked Facebook Page is not required.
Use the Instagram-specific application ID and secret displayed in the product
settings; do not assume they match the parent application's credentials.

1. Request `instagram_business_basic` and
   `instagram_business_manage_messages`.
2. Register the exact redirect URI
   `https://YOUR_ORIGIN/api/social/oauth/callback/instagram`.
3. Configure the webhook callback
   `https://YOUR_ORIGIN/api/public/social/instagram/webhook` and the configured
   verification token.
4. Enable `messages`, `messaging_postbacks`, `messaging_seen`,
   `message_reactions`, `messaging_referral`, `messaging_handover`, and
   `standby` subscriptions.
5. Complete review and access requirements for the accounts being served.
6. In the client's Instagram channel settings, choose an agent, authorize the
   account, then confirm the returned account.

The authorization flow requests a short-lived token, exchanges it for a
long-lived token, and stores only encrypted credentials. Long-lived Instagram
tokens normally last 60 days. Eligible tokens are refreshed before expiration;
an expired or revoked token requires authorization again.

Meta documents separate Instagram Login and Facebook Login setup modes. Do not
mix their tokens, API hosts, permissions, or account IDs. This implementation
uses direct Instagram Login and a separate Messenger connector.

### Facebook Messenger

Use a **Facebook Page**, Facebook Login for Business, and the Messenger product.
The authorizing person must have the Page tasks needed for messaging and webhook
management. The connection lists Pages returned by `/me/accounts` and requires
`MESSAGING` and `MODERATE` tasks.

Use a login configuration that returns a User access token, so the server can
exchange it and discover the Pages the person authorized. A configuration that
returns a system-user token uses a different authorization lifecycle.

1. Configure `pages_show_list`, `pages_messaging`, `pages_manage_metadata`,
   `pages_read_engagement`, and `business_management` as required by the current
   Messenger permission dependencies and your login configuration.
2. Register the exact redirect URI
   `https://YOUR_ORIGIN/api/social/oauth/callback/messenger`.
3. Configure the webhook callback
   `https://YOUR_ORIGIN/api/public/social/messenger/webhook` and the configured
   verification token.
4. Enable `messages`, `messaging_postbacks`, `message_deliveries`,
   `message_reads`, `messaging_referrals`, `message_echoes`,
   `messaging_handovers`, and `standby`.
5. Complete the access review and business verification that apply to the app.
6. Choose an agent, authorize access, then select the Page to connect.

User tokens obtained during authorization are exchanged before Page discovery.
Only the selected Page token is stored on the channel. Page tokens can become
invalid after permission, role, password, security, or account changes. The
worker checks Page authorization daily and marks expired or revoked
connections for authorization again. Never assume a Page token is permanent.

## Manual credentials

An operator may use the manual configuration section instead of browser
OAuth. Enter the application ID, receiving account ID, access token, matching
application secret, and assigned agent. For Instagram, provide a valid
long-lived Instagram User token; for Messenger, provide a Page token.

1. Save the credentials. OpenLivery validates account identity and messaging
   access, stores a disabled draft, and displays its webhook URL and verification
   token. This first save does not activate message processing.
2. Configure Meta to call the displayed per-channel URL
   `/api/public/social/channels/CHANNEL_ID/webhook`, using the displayed token.
3. Enable the provider's webhook fields listed above.
4. Press **Connect**. OpenLivery subscribes the account, reads the subscription
   back, and activates the connection only after confirmation.

The API keeps saved credentials when their form fields are submitted blank.
A connected channel cannot be repointed to a different external account: old
conversations must continue to reference the account that received them.
Disconnect removes local credentials and attempts to remove the app's remote
subscription. If Meta is unreachable or authorization was already revoked,
OpenLivery disconnects locally and reports that remote removal could not be
confirmed. Check the account's application settings in that case.

## Inbox behavior and limits

Each sender is identified by provider, receiving account, and the provider's
scoped sender ID. A sender ID is not a telephone number and is not globally
unique. Identical names or numeric IDs on different receiving accounts must not
silently merge contacts. Manual contact merging can group identities while
preserving the channel that each conversation uses for replies.

Normal replies, including automated agent replies, are limited to the standard
24-hour window following qualifying user activity. Human Agent access can allow
human support through seven days when the app has that approved capability.
Enable the setting only after approval. It must never be used to extend an
agent's automated reply window. A tag does not create permission to send
unsolicited messages.

Instagram text is limited by UTF-8 bytes, not just characters. Attachments must
meet the receiving provider's media and size requirements. WhatsApp-specific
voice encodings and approved templates do not transfer automatically to these
channels.

Inbound messages retain up to ten supported attachments within a 20 MB total
per-message budget. Unavailable, unsupported, or over-limit files receive an
explicit placeholder. Instagram uploads normalize supported image/audio formats;
other file types must satisfy its API limits.

The connector captures new events after connection. The **Import available
history** action schedules a durable background job for up to 20 conversations
and the 20 most recent accessible message details per conversation. The status
shows progress and provider errors. When more conversations remain, requesting
another batch continues from the saved cursor. An interrupted batch resumes its
checkpoint without duplicating recorded messages.

Only messages predating the connection are eligible. Imported messages preserve
their original timestamps and never schedule an automated reply, reopen a reply
window, or send a new-message notification. Provider-inaccessible media retains
an unavailable-content marker. This is not a guarantee of complete history:
Meta limits message detail availability, and Instagram excludes some old
requests. Locally recorded unread state and native-inbox read state are different
concepts.

Imported archives remain resolved and do not count as new inbox activity in
message reports. New live messages start or join an active case normally.

An agent failure routes the case to a person instead of silently abandoning the
incoming message or rerunning tools with possible side effects. When the agent
requests a handover, its farewell is processed by the delivery queue first;
then the conversation enters human mode. A failed farewell still hands over.

Human replies from native apps arrive as provider echo events. Verify these
with the actual app's conversation routing settings before combining multiple
inbox applications. Platform-level conversation ownership and OpenLivery's
AI/human switch are separate mechanisms.

## Operations and security

- Webhook POSTs must have a valid `X-Hub-Signature-256` for the relevant app.
  The verification-token handshake alone does not authenticate message events.
- OAuth state is random, hashed at rest, expiring, bound to the user/client/agent,
  and consumed once. Account-selection requests also require the original
  signed-in user. Tokens are not returned to the browser or placed in redirect
  URLs.
- Temporary account choices are encrypted. Completed choices are scrubbed.
  Configure retention of expired connection state and provider data consistent
  with the installation's privacy and deletion policy.
- Requests only target fixed official API hosts. Pagination follows cursor
  values, never an arbitrary `paging.next` URL supplied by a response.
- The HTTP client redacts token-exchange query parameters from its request
  logs. Configure reverse proxies and observability tools to redact OAuth
  callback query parameters, authorization headers, and request bodies too.
- Authentication failures require reconnecting. Rate limits and transient
  failures require bounded retries; never repeatedly replay an uncertain send
  without checking its delivery state.
- A failed remote subscription or local transaction must not replace the
  credentials of an existing healthy connection.

Deployments can provide application configuration through
`register_app_config_resolver()`. Connection and OAuth-state hooks use the same
SQLAlchemy transaction as the core operation. Hook implementations must preserve
ownership, isolation, and rollback behavior. Background work must use the
configured session factory and preserve its database context.

## Live-account acceptance checks

Run automated tests against an isolated database. Then validate the following
with professional accounts and a Page whose administrators authorized testing:

1. Authorize, cancel, reconnect, select a different Page, and decline a required
   permission. No token appears in the browser URL, API responses, or logs.
2. Confirm a sender without an application role can send a message when the app
   is intended to serve public users. Successful administrator testing alone
   does not prove the access review is complete.
3. Receive text and supported attachments; check the correct client, account,
   contact, and agent. Replay the identical signed event and verify one message.
4. Send human and automated replies, then reply from the native application.
   Verify no echo loop or duplicate automated reply.
5. Test the 24-hour boundary, approved Human Agent support, and expired-window
   refusal. A human toggle must not let the AI send tagged messages.
6. Revoke access and disable the account. Confirm local status and blocked sends,
   then authorize again and verify conversations retain the same account identity.
7. Retry after provider throttling and restart the API while queued events exist.
   Check durable recovery without crossing clients or duplicating uncertain sends.
8. Verify the app's privacy policy, data-deletion instructions, review artifacts,
   and conversation routing configuration in the developer dashboard.

Automated mocks validate application behavior, not Meta review approval or
real-account delivery.

## Official references

- [Instagram Login](https://developers.facebook.com/documentation/instagram-platform/instagram-api-with-instagram-login)
- [Instagram authorization and token refresh](https://developers.facebook.com/documentation/instagram-platform/instagram-api-with-instagram-login/business-login)
- [Instagram messaging](https://developers.facebook.com/documentation/instagram-platform/instagram-api-with-instagram-login/messaging-api)
- [Instagram webhooks](https://developers.facebook.com/documentation/instagram-platform/webhooks)
- [Instagram subscription field names in Meta's SDK](https://github.com/facebook/facebook-python-business-sdk/blob/25.0.0/facebook_business/adobjects/iguserforigonlyapi.py#L672)
- [Instagram access review](https://developers.facebook.com/documentation/instagram-platform/app-review)
- [Messenger overview](https://developers.facebook.com/documentation/business-messaging/messenger-platform/overview)
- [Messenger webhooks](https://developers.facebook.com/documentation/business-messaging/messenger-platform/webhooks)
- [Messenger policy](https://developers.facebook.com/documentation/business-messaging/messenger-platform/policy)
