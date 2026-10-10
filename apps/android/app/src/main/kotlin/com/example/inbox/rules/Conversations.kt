package com.example.inbox.rules

import com.example.inbox.api.Conversation
import com.example.inbox.api.ConversationDetail
import com.example.inbox.localization.Strings
import com.example.inbox.localization.WorkspaceStrings

/**
 * What to call a conversation.
 *
 * The title the server stores is the first thing the customer typed, which is
 * fine as a database label and wrong as a name. So the name is the person, the
 * way it is in any messaging app, and when nobody gave a name, the next most
 * identifying thing the channel knows.
 */
object Conversations {
    /** `573001234567@s.whatsapp.net` -> `+573001234567`. */
    fun phone(externalChatId: String?): String? {
        val address = externalChatId ?: ""
        // Group and linked-device identifiers are not telephone numbers.
        if (Regex("@(?:g\\.us|lid)$").containsMatchIn(address)) return null
        val local = address.substringBefore("@")
        val beforeColon = local.substringBefore(":")
        val digits = beforeColon.filter { it.isDigit() }
        // Short enough to be a group id or a placeholder rather than a number.
        return if (digits.length >= 7) "+$digits" else null
    }

    fun channelLabel(channel: String): String {
        val s = Strings.current.channels
        if (InboxRules.isWhatsApp(channel)) return s.whatsapp
        return when (channel) {
            "widget" -> s.widget
            "playground" -> s.playground
            "instagram" -> s.instagram
            "messenger" -> s.messenger
            else -> channel
        }
    }

    /** A longer label where WhatsApp Business is distinguished from the bridge. */
    fun channelName(channel: String): String = when (channel) {
        "whatsapp_cloud" -> "WhatsApp Business"
        "whatsapp" -> "WhatsApp"
        "instagram" -> "Instagram"
        "messenger" -> "Facebook Messenger"
        "widget" -> WorkspaceStrings.current.web
        else -> channel
    }

    /** Who this conversation is with. */
    fun name(c: Conversation): String {
        val named = (c.contactName ?: "").trim()
        if (named.isNotEmpty()) return named
        if (InboxRules.isWhatsApp(c.channel)) phone(c.externalChatId)?.let { return it }
        if (c.channel == "widget") return Strings.current.list.webVisitor
        val title = c.title.trim()
        return title.ifEmpty { Strings.current.list.untitled }
    }

    fun name(c: ConversationDetail): String = name(c.summary)

    /** The letter shown in the avatar when there is no picture. */
    fun initial(name: String): String {
        var value = name.trim()
        if (value.startsWith("+")) value = value.drop(1)
        value = value.trim()
        val first = value.firstOrNull() ?: return "?"
        return first.toString().uppercase()
    }
}
