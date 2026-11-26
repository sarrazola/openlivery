# Telegram

A client's agent can answer the private chats of a Telegram bot. The bot is
connected with the token @BotFather issues for it; there is no application to
create and no review to pass. Conversations appear in the inbox next to the
other channels, and a person can take any of them over.

## Create the bot

1. Open [@BotFather](https://t.me/BotFather) in Telegram and send `/newbot`.
2. Choose the bot's display name and a username that ends in `bot`.
3. Copy the token BotFather replies with (`123456789:AA…`). Anyone holding it
   controls the bot, so treat it like a password.

## Connect it

Open the client, then **Channels** and **Telegram**. Pick the agent that
answers, optionally a name for the inbox, paste the token and choose
**Connect bot**. OpenLivery checks the token with Telegram, stores it encrypted
and points the bot's webhook at this deployment. A client can connect several
bots; a bot belongs to one client at a time.

The webhook needs a public HTTPS origin. It is built from `SOCIAL_PUBLIC_URL`,
or `FRONTEND_URL` when that is empty; on a local machine, expose the stack with a
tunnel and set `SOCIAL_PUBLIC_URL` to its address before connecting. If the
address changes later, open the bot and choose **Check connection** to point the
webhook at the new one.

## What it handles

- **Private chats only.** Messages in groups and channels are ignored.
- **No reply window.** A person starts the chat by opening the bot (Telegram
  sends `/start`, which the agent reads as an opened chat). From then on the
  agent and the team can reply at any time.
- **Files both ways.** Text, photos, voice notes, audio, videos, documents and
  static stickers arrive in the inbox, up to the 20 MB Telegram lets a bot
  download. Voice notes are transcribed and images described when the agent has
  those capabilities. Replies can carry files: photos, voice notes (browser
  recordings are converted to Ogg Opus), videos and documents.
- **Formatting.** Agents write Markdown; the copy sent to Telegram uses
  Telegram's own formatting (bold, italics, links, code). If Telegram refuses
  the markup, the reply goes out as plain text.
- **Typing.** While the agent writes, the chat shows the bot typing. Bots
  cannot mark messages as read.
- Follow-ups, escalation, contact capture, teams and summaries work as on the
  other channels.

## When something fails

- A contact who blocked the bot or deleted the chat cannot receive messages; the
  reply is marked as not delivered and the bot stays connected.
- A token revoked in BotFather stops every reply and the bot shows that it needs
  a new token. Paste the new one under **Bot token** and save.
- **Disconnect** removes the webhook and the bot from the client. Its
  conversations stay in the inbox as history; the bot itself keeps existing in
  Telegram.
