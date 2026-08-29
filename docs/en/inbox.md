# Inbox

> Leer en español: [inbox.md](../es/inbox.md)

The Inbox is a single place to watch every conversation your agents are having, search across them, and step in as a human when the AI needs help. It pulls together conversations from every channel — the playground, [WhatsApp](whatsapp.md) and the [web widget](web-widget.md) — into one list.

## Unified list

Every conversation shows the contact name (or title), a preview of the latest message, the agent that owns it, the channel it came from, and a badge marking whether it is in **AI** or **human** mode. The list is scoped to your agency, so operators only see their own tenant's conversations.

Two filters at the top narrow the view: by **agent** and by **channel** (playground, WhatsApp or widget). These combine with the tabs and search below.

## Search and tabs

A search box runs **server-side**: it matches the conversation title, the contact name, and the content of the latest message. Input is debounced, so results update shortly after you stop typing.

Four tabs filter the list:

- **All** — every conversation.
- **Unread** — conversations whose latest message is from the visitor and hasn't been read since.
- **Human** — conversations currently in human mode.
- **AI** — conversations currently handled by the agent.

## Unread tracking and pagination

Unread is derived from an `operator_read_at` timestamp: a conversation counts as unread when its last message came from the visitor and arrived after you last opened it. Opening a conversation marks it read. The first page refreshes automatically every few seconds so new messages surface without a manual reload. The list loads in pages of 30 and fetches more as you scroll toward the bottom.

## Human takeover

Each conversation carries a `mode` field. In **AI** mode the agent answers automatically. Use **Take control** to switch the conversation to **human** mode: this pauses the AI so an operator can reply in its place. While a conversation is in human mode the AI will not generate replies — attempts to do so are rejected until you hand it back. When you're done, **Return to AI** flips the mode back and the agent resumes.

This is the same `mode` concept used for [WhatsApp](whatsapp.md) conversations, so taking over works consistently regardless of channel.

## Who can take over

Both agency operators (from this Inbox) and client users can take over conversations. Client users do it from the [client portal](client-portal.md), which exposes the same take-control and reply-as-human actions scoped to their client.
