package com.example.inbox.rules

import com.example.inbox.api.ChannelCapabilities
import com.example.inbox.api.Conversation
import com.example.inbox.api.ConversationDetail
import com.example.inbox.api.ConversationMode
import com.example.inbox.api.ConversationStatus
import com.example.inbox.api.Message
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Error
import androidx.compose.material.icons.filled.Help
import androidx.compose.material.icons.filled.Schedule
import androidx.compose.ui.graphics.vector.ImageVector
import java.time.Instant

/**
 * Rules shared by inbox lists and thread actions.
 *
 * The server enforces all of them. They are mirrored here so the composer can
 * close itself between polling ticks, instead of offering a reply the server
 * is about to refuse.
 */
object InboxRules {
    fun isSocialChannel(channel: String) = channel == "instagram" || channel == "messenger"
    fun isWhatsApp(channel: String) = channel == "whatsapp" || channel == "whatsapp_cloud"

    private fun windowIsOpen(open: Boolean?, until: String?, now: Instant): Boolean {
        if (open != true) return false
        val limit = IsoDate.parse(until) ?: return false
        return limit.isAfter(now)
    }

    fun isReplyWindowClosed(c: ConversationDetail, now: Instant = Instant.now()): Boolean {
        if (isSocialChannel(c.channel)) {
            if (!c.replyBlockReason.isNullOrEmpty()) return true
            return !windowIsOpen(c.humanReplyWindowOpen, c.humanReplyWindowUntil, now) && !windowIsOpen(c.replyWindowOpen, c.replyWindowUntil, now)
        }
        if (c.channel != "whatsapp_cloud") return false
        if (!c.replyWindowOpen) return true
        val until = IsoDate.parse(c.replyWindowUntil) ?: return false
        return !until.isAfter(now)
    }

    fun canReply(c: ConversationDetail, now: Instant = Instant.now()): Boolean =
        c.status != ConversationStatus.RESOLVED && c.mode == ConversationMode.HUMAN && !isReplyWindowClosed(c, now)

    fun capabilities(c: ConversationDetail): ChannelCapabilities {
        if (isSocialChannel(c.channel)) return c.channelCapabilities ?: ChannelCapabilities()
        return (c.channelCapabilities ?: ChannelCapabilities()).mergedOver(ChannelCapabilities.everything)
    }

    fun acceptsAttachment(channel: String, capabilities: ChannelCapabilities, mime: String): Boolean {
        var isFile = false
        val kind = when {
            mime.startsWith("image/") -> capabilities.image
            mime.startsWith("audio/") -> capabilities.audio
            mime.startsWith("video/") -> capabilities.video
            else -> { isFile = true; capabilities.file }
        }
        return kind == true && !(channel == "instagram" && isFile && mime != "application/pdf")
    }

    /** The approved human window is open but the automated one is not. */
    fun humanWindowOnly(c: ConversationDetail, now: Instant = Instant.now()): Boolean =
        isSocialChannel(c.channel) && !isReplyWindowClosed(c, now) && !windowIsOpen(c.replyWindowOpen, c.replyWindowUntil, now)

    /** The label key and icon for a delivery state the channel reported. */
    fun delivery(status: String?): Pair<String, ImageVector>? {
        if (status.isNullOrEmpty()) return null
        return when (status) {
            "read", "delivered" -> status to Icons.Default.CheckCircle
            "sent" -> "sent" to Icons.Default.Check
            "failed" -> "failed" to Icons.Default.Error
            "pending" -> "pending" to Icons.Default.Schedule
            else -> "unknown" to Icons.Default.Help
        }
    }

    fun canQuote(c: ConversationDetail, message: Message, now: Instant = Instant.now()): Boolean =
        canReply(c, now) && c.channelCapabilities?.quotes != false && isWhatsApp(c.channel) && !message.isActivity && message.role != "system"

    fun canReact(c: ConversationDetail, message: Message): Boolean =
        c.status != ConversationStatus.RESOLVED && c.mode == ConversationMode.HUMAN && c.channelCapabilities?.reactions != false &&
            isWhatsApp(c.channel) && !message.isActivity && message.role == "user"

    /** The same placeholders the web fills: the contact's details and the operator's name. */
    data class CannedVariables(val contactName: String, val contactPhone: String, val contactEmail: String, val agentName: String)

    fun interpolate(content: String, v: CannedVariables): String {
        val values = mapOf(
            "contact_name" to v.contactName, "contact_phone" to v.contactPhone, "contact_email" to v.contactEmail,
            "agent_name" to v.agentName, "my_name" to v.agentName,
        )
        var result = content
        // Unknown or empty values stay visible so the operator notices and edits before sending.
        for ((key, value) in values) if (value.isNotEmpty()) result = result.replace("{$key}", value)
        return result
    }

    /** A row's time follows the customer's message, never an operator action. */
    fun timestamp(c: Conversation): String = listOfNotNull(c.lastInboundAt, c.createdAt, c.updatedAt).firstOrNull { it.isNotEmpty() } ?: ""

    /** Offset pagination can overlap when inbound messages move existing rows. */
    fun mergePages(previous: List<Conversation>, incoming: List<Conversation>): List<Conversation> {
        val order = ArrayList<String>()
        val byId = HashMap<String, Conversation>()
        for (row in previous + incoming) {
            if (!byId.containsKey(row.id)) order.add(row.id)
            byId[row.id] = row
        }
        return order.mapNotNull { byId[it] }
    }
}
