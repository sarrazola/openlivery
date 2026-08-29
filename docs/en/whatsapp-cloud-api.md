# Connecting the WhatsApp Business Cloud API

> Leer en español: [whatsapp-cloud-api.md](../es/whatsapp-cloud-api.md)

This guide walks through connecting a client's WhatsApp number to OpenLivery
using the official **WhatsApp Business Cloud API** (hosted by Meta): from
creating the Meta app to pasting the credentials into OpenLivery and going
live. It is independent from the WhatsApp QR channel — a client can have both
connected on different numbers.

At the end you will have entered four values into OpenLivery:

| Value | Where it comes from |
| --- | --- |
| **Phone number ID** | Meta Developer Portal → WhatsApp → API Setup |
| **WhatsApp Business account ID** (optional) | Same screen as the phone number ID |
| **Permanent access token** | A Business Suite *system user* (step 4) |
| **App secret** | App Dashboard → App settings → Basic |

## 1. Prerequisites

Before the technical setup, make sure you have:

- A **Meta Business Portfolio** (formerly Business Manager) in good standing:
  - **Business verification** completed — check it under
    **Settings > Business Info > Verification Status**.
  - A **payment method** linked to the WhatsApp account inside Business Suite
    to cover conversation costs.
- A phone number that can receive an SMS or voice verification call and is
  **not** currently registered on the WhatsApp/WhatsApp Business apps.
- An OpenLivery instance reachable over **public HTTPS** (Meta only delivers
  webhooks to HTTPS URLs), with the client created and an agent assigned to it.

## 2. Create the Meta app

1. Go to the [Meta for Developers](https://developers.facebook.com/) portal.
2. Click **Create App**.
3. As the app type choose **Other**, then **Business**.
4. Inside the App Dashboard find the **WhatsApp** product and click **Set Up**.
5. When asked, link the app to your **verified Business Portfolio**.

## 3. Configure the WhatsApp number

1. In the Developer Portal go to **WhatsApp > API Setup**.
2. **Add phone number** and follow the prompts to add the business number.
3. Choose a **display name** that clearly represents the brand (for example,
   "Di Pizza Gourmet").
   - Meta reviews this name. If it is rejected, use **Edit Display Name** to
     provide a more specific, non-generic one.
4. Complete the **SMS or voice verification** for the number.
5. Copy the **Phone number ID** shown on this screen — you will paste it into
   OpenLivery. The **WhatsApp Business account ID** (WABA ID) appears on the
   same screen and is optional in OpenLivery.

## 4. Generate a permanent access token

The token shown on the API Setup screen expires in 24 hours. For a permanent
connection, create one through a system user:

1. Go to **Meta Business Suite > Settings > Users > System Users**.
2. Select an existing **Admin system user**, or create one.
3. Click **Assign Assets**, choose **Apps**, select your WhatsApp app and
   enable **Full Control (Manage App)**.
4. Click **Generate New Token**, select the app, and check these scopes:
   - `whatsapp_business_messaging`
   - `whatsapp_business_management`
5. **Copy the token immediately and store it safely** — Meta will not show it
   again. This is the **Permanent access token** for OpenLivery.

## 5. Get the app secret

1. In the App Dashboard go to **App settings > Basic**.
2. Click **Show** next to **App secret** and copy it.

OpenLivery uses the app secret to validate the HMAC signature of every
webhook Meta sends, so requests that are not really from Meta are rejected.

## 6. Enter the credentials in OpenLivery

1. In OpenLivery open **Clients**, pick the client, and on its **Channels**
   tab open the **WhatsApp API** card (also reachable from the **Channels**
   page).
2. Select the **agent** that will answer this number.
3. Fill in:
   - **Phone number ID** (from step 3)
   - **WhatsApp Business account ID** — optional
   - **Permanent access token** (from step 4)
   - **App secret** (from step 5)
4. Click **Save credentials**. The token and secret are encrypted at rest and
   are write-only: the API never returns them, and leaving them blank on a
   later save keeps the stored values.

## 7. Register the webhook

Still on the channel page, OpenLivery shows a **Callback URL** and a
**Verify token** with copy buttons:

1. In the Meta Developer Portal go to **WhatsApp > Configuration**.
2. Paste the **Callback URL** and the **Verify token**, then save. Meta calls
   the URL once to verify the handshake — it must succeed before you can
   continue.
3. Under **Webhooks**, click **Manage** and subscribe to the **`messages`**
   field.

> The callback URL is built from the instance's public address, so the
> instance must be reachable over HTTPS at that URL. If the handshake fails,
> see the troubleshooting section.

## 8. Connect and go live

1. Back in OpenLivery click **Connect and verify**. OpenLivery validates the
   credentials against the Graph API and captures the number and its verified
   name; the channel status changes to **connected**.
2. In the Developer Portal switch the **App Mode** from **Development** to
   **Live** (top bar) so real customer traffic can flow.
3. Send a WhatsApp message to the number: the assigned agent should answer,
   and the conversation appears in the OpenLivery Inbox.

## 9. Troubleshooting

- **Authorization error** — usually an expired token or missing permissions
  (`whatsapp_business_messaging`). Generate a new permanent token (step 4)
  and save it again in OpenLivery.
- **Display name pending or rejected** — make sure the display name matches
  the legal business name or the website branding.
- **Payment required** — the payment method must be assigned specifically to
  the **WhatsApp account** in Business Suite, not just to the general Ad
  Account.
- **Webhook verification fails** — the verify token pasted in Meta must match
  the one OpenLivery shows exactly, and the callback URL must be reachable
  from the internet over HTTPS. On self-hosted instances, check that
  `FRONTEND_URL` points to the public address of the app.
- **No messages arrive** — confirm the subscription to the **`messages`**
  webhook field (step 7), and that the app is in **Live** mode; in
  Development mode Meta only delivers traffic from test numbers. The channel
  card in OpenLivery shows the last webhook error, if any.
- **Messages arrive but the agent does not answer** — the channel is
  connected but the assigned agent may be inactive or missing its provider
  API key; the channel card shows the exact reason under **last error**.
