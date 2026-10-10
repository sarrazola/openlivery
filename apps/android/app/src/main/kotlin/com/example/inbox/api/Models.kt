package com.example.inbox.api

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.jsonPrimitive

/// What the portal API returns. Keys arrive in snake_case and the shared Json
/// maps them to these camelCase names, so nothing here spells a wire key.

@Serializable
data class Branding(
    val agencyName: String = "",
    val clientName: String = "",
    val portalTitle: String = "",
    val brandColor: String = "",
    val agencyLogoUrl: String? = null,
    val clientLogoUrl: String? = null,
)

/** How the server expects to be able to notify this app; `enabled = false` means initialise nothing. */
@Serializable
data class PushConfig(val enabled: Boolean = false, val provider: String = "none")

@Serializable
data class PrivacyDestination(val kind: String, val name: String = "", val host: String = "", val capabilities: List<String> = emptyList())

@Serializable
data class PrivacyDisclosure(val version: String = "", val destinations: List<PrivacyDestination> = emptyList())

@Serializable
data class Session(
    val token: String,
    val portalSlug: String,
    val clientId: String,
    val userId: String? = null,
    val userName: String = "",
    val role: String? = null,
    val permissions: List<String>? = null,
    val branding: Branding,
    val push: PushConfig = PushConfig(),
    val apiVersion: Int = 1,
    val privacy: PrivacyDisclosure? = null,
) {
    /** The server's current grants are authoritative, including an empty list. */
    fun has(permission: String): Boolean = permissions?.contains(permission) ?: false
}

@Serializable
data class HostedAccount(val server: String, val session: Session) {
    val id: String get() = "$server|${session.clientId}|${session.userId ?: ""}"
}

@Serializable
data class HostedSignInResponse(val accounts: List<HostedAccount> = emptyList())

@Serializable
data class Attachment(val id: String, val kind: String = "", val mime: String = "", val filename: String? = null, val sizeBytes: Long = 0)

@Serializable
enum class ConversationMode { @SerialName("ai") AI, @SerialName("human") HUMAN }

@Serializable
enum class ConversationStatus { @SerialName("open") OPEN, @SerialName("resolved") RESOLVED }

@Serializable
enum class Availability { @SerialName("online") ONLINE, @SerialName("away") AWAY }

/** What a channel accepts; `null` means the server did not say, which reads as allowed. */
@Serializable
data class ChannelCapabilities(
    val text: Boolean? = null,
    val image: Boolean? = null,
    val audio: Boolean? = null,
    val video: Boolean? = null,
    val file: Boolean? = null,
    val quotes: Boolean? = null,
    val reactions: Boolean? = null,
    val templates: Boolean? = null,
) {
    fun mergedOver(base: ChannelCapabilities): ChannelCapabilities = ChannelCapabilities(
        text ?: base.text, image ?: base.image, audio ?: base.audio, video ?: base.video,
        file ?: base.file, quotes ?: base.quotes, reactions ?: base.reactions, templates ?: base.templates,
    )

    companion object {
        val everything = ChannelCapabilities(true, true, true, true, true, true, true, true)
    }
}

@Serializable
data class Message(
    val id: String,
    val role: String = "",
    val kind: String = "message",
    /** The event name and its variables on an activity row. */
    val activity: JsonObject? = null,
    val content: String = "",
    val senderType: String = "",
    val senderName: String? = null,
    val externalMessageId: String? = null,
    val deliveryStatus: String? = null,
    val deliveryError: String? = null,
    val reaction: String? = null,
    val incomingReaction: String? = null,
    val quotedMessageId: String? = null,
    val createdAt: String = "",
    val attachments: List<Attachment> = emptyList(),
) {
    val isActivity: Boolean get() = kind == "activity"
    val isOutgoing: Boolean get() = role == "assistant"
    val isAI: Boolean get() = isOutgoing && senderType == "ai"

    /** How a variable reads inside an activity sentence. */
    fun activityValue(key: String): String? {
        val value = activity?.get(key) ?: return null
        val primitive = value as? JsonPrimitive ?: return null
        val raw = primitive.content
        return if (!primitive.isString) raw.toDoubleOrNull()?.let { if (it == Math.floor(it)) it.toLong().toString() else raw } ?: raw else raw
    }
}

/** A file staged for sending: where it is, what to call it and its type. */
data class OutgoingFile(val file: java.io.File, val name: String, val mime: String) {
    val isAudio: Boolean get() = mime.startsWith("audio/")
}

/** The list row: everything a conversation is, except its messages. */
@Serializable
data class Conversation(
    val id: String,
    val clientId: String = "",
    val agentId: String = "",
    val title: String = "",
    val mode: ConversationMode = ConversationMode.HUMAN,
    val status: ConversationStatus = ConversationStatus.OPEN,
    val channel: String = "",
    val externalChatId: String? = null,
    val contactName: String? = null,
    val contactId: String? = null,
    val contactEmail: String? = null,
    val preview: String = "",
    val unread: Boolean = false,
    val unreadCount: Int = 0,
    val assigneeId: String? = null,
    val assigneeName: String? = null,
    val teamId: String? = null,
    val teamName: String? = null,
    val replyWindowUntil: String? = null,
    val replyWindowOpen: Boolean = true,
    val humanReplyWindowOpen: Boolean? = null,
    val humanReplyWindowUntil: String? = null,
    val replyBlockReason: String? = null,
    val socialChannelId: String? = null,
    val channelCapabilities: ChannelCapabilities? = null,
    val lastInboundAt: String? = null,
    val resolvedAt: String? = null,
    val firstReplyAt: String? = null,
    val takenOverAt: String? = null,
    val waitingSince: String? = null,
    val createdAt: String = "",
    val updatedAt: String = "",
)

/** A conversation with its messages. */
@Serializable
data class ConversationDetail(
    val id: String,
    val clientId: String = "",
    val agentId: String = "",
    val title: String = "",
    val mode: ConversationMode = ConversationMode.HUMAN,
    val status: ConversationStatus = ConversationStatus.OPEN,
    val channel: String = "",
    val externalChatId: String? = null,
    val contactName: String? = null,
    val contactId: String? = null,
    val contactEmail: String? = null,
    val preview: String = "",
    val unread: Boolean = false,
    val unreadCount: Int = 0,
    val assigneeId: String? = null,
    val assigneeName: String? = null,
    val teamId: String? = null,
    val teamName: String? = null,
    val replyWindowUntil: String? = null,
    val replyWindowOpen: Boolean = true,
    val humanReplyWindowOpen: Boolean? = null,
    val humanReplyWindowUntil: String? = null,
    val replyBlockReason: String? = null,
    val socialChannelId: String? = null,
    val channelCapabilities: ChannelCapabilities? = null,
    val lastInboundAt: String? = null,
    val resolvedAt: String? = null,
    val firstReplyAt: String? = null,
    val takenOverAt: String? = null,
    val waitingSince: String? = null,
    val createdAt: String = "",
    val updatedAt: String = "",
    val messages: List<Message> = emptyList(),
) {
    /** The list row shape, for everything that reasons about a conversation without its messages. */
    val summary: Conversation
        get() = Conversation(
            id, clientId, agentId, title, mode, status, channel, externalChatId, contactName, contactId, contactEmail, preview, unread,
            unreadCount, assigneeId, assigneeName, teamId, teamName, replyWindowUntil, replyWindowOpen, humanReplyWindowOpen,
            humanReplyWindowUntil, replyBlockReason, socialChannelId, channelCapabilities, lastInboundAt, resolvedAt, firstReplyAt,
            takenOverAt, waitingSince, createdAt, updatedAt,
        )

    companion object {
        /** A row opened from the list, before its messages have loaded. */
        fun opening(c: Conversation): ConversationDetail = ConversationDetail(
            c.id, c.clientId, c.agentId, c.title, c.mode, c.status, c.channel, c.externalChatId, c.contactName, c.contactId, c.contactEmail,
            c.preview, c.unread, c.unreadCount, c.assigneeId, c.assigneeName, c.teamId, c.teamName, c.replyWindowUntil, c.replyWindowOpen,
            c.humanReplyWindowOpen, c.humanReplyWindowUntil, c.replyBlockReason, c.socialChannelId, c.channelCapabilities, c.lastInboundAt,
            c.resolvedAt, c.firstReplyAt, c.takenOverAt, c.waitingSince, c.createdAt, c.updatedAt, emptyList(),
        )
    }
}

@Serializable
data class InboxSummary(
    val open: Int = 0, val resolved: Int = 0, val human: Int = 0, val ai: Int = 0,
    val unread: Int = 0, val mine: Int = 0, val unassigned: Int = 0,
)

@Serializable
data class PortalMember(val id: String, val name: String = "", val email: String = "", val availability: Availability = Availability.AWAY)

@Serializable
data class Team(
    val id: String,
    val name: String = "",
    val description: String = "",
    val strategy: String = "round_robin",
    val channels: List<String> = emptyList(),
    val isDefault: Boolean = false,
    val members: List<PortalMember> = emptyList(),
    val openCount: Int = 0,
    val unassignedCount: Int = 0,
)

@Serializable
data class ContactTag(
    val id: String,
    val name: String = "",
    val color: String = "#6b7280",
    val contactCount: Int = 0,
    val routeTeamId: String? = null,
    val routeTeamName: String? = null,
    val routeAssigneeId: String? = null,
    val routeAssigneeName: String? = null,
)

@Serializable data class ContactTagCreate(val name: String, val color: String? = null)
@Serializable data class ContactTagUpdate(val name: String? = null, val color: String? = null)
@Serializable data class ContactTagsSet(val tagIds: List<String>)

@Serializable
data class CannedReply(val id: String, val shortcut: String = "", val content: String = "", val updatedAt: String = "")

@Serializable data class CannedReplyCreate(val shortcut: String, val content: String)
@Serializable data class CannedReplyUpdate(val shortcut: String? = null, val content: String? = null)

@Serializable
data class Contact(
    val id: String,
    val name: String = "",
    val phone: String? = null,
    val email: String? = null,
    val notes: String = "",
    val tags: List<ContactTag>? = null,
    val createdAt: String = "",
    val updatedAt: String = "",
    val conversationCount: Int = 0,
    val openCount: Int = 0,
    val lastActivityAt: String? = null,
)

@Serializable data class ContactCreate(val name: String? = null, val phone: String, val email: String? = null, val notes: String? = null)

/** A PATCH body: an absent field keeps its value; `clearEmail` sends `email: null`. */
data class ContactUpdate(val name: String? = null, val phone: String? = null, val email: String? = null, val clearEmail: Boolean = false, val notes: String? = null) {
    fun toJson(): String {
        val parts = ArrayList<String>()
        fun quote(value: String) = "\"" + value.replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", "\\n") + "\""
        name?.let { parts.add("\"name\":${quote(it)}") }
        phone?.let { parts.add("\"phone\":${quote(it)}") }
        if (email != null) parts.add("\"email\":${quote(email)}") else if (clearEmail) parts.add("\"email\":null")
        notes?.let { parts.add("\"notes\":${quote(it)}") }
        return "{" + parts.joinToString(",") + "}"
    }
}

@Serializable
data class TeamUpdate(
    val name: String, val description: String = "", val strategy: String = "round_robin", val channels: List<String> = emptyList(),
    val isDefault: Boolean = false, val memberIds: List<String> = emptyList(),
)

@Serializable data class ReportDay(val date: String = "", val started: Int = 0, val resolved: Int = 0)
@Serializable data class ReportChannel(val channel: String = "", val started: Int = 0)
@Serializable data class ReportAgent(val name: String = "", val availability: String = "", val replies: Int = 0, val assigned: Int = 0, val openNow: Int = 0)

@Serializable
data class PortalReport(
    val started: Int = 0, val resolved: Int = 0, val openNow: Int = 0, val inboundMessages: Int = 0, val humanReplies: Int = 0,
    val aiReplies: Int = 0, val activeContacts: Int = 0, val agentsOnline: Int = 0, val avgFirstReplySeconds: Double? = null,
    val avgResolutionSeconds: Double? = null, val byDay: List<ReportDay> = emptyList(), val byChannel: List<ReportChannel> = emptyList(),
    val byAgent: List<ReportAgent> = emptyList(),
)

@Serializable
data class PortalChannel(
    val channel: String = "", val status: String = "", val phoneNumber: String? = null, val displayName: String? = null,
    val supportsTemplates: Boolean = false, val id: String? = null, val provider: String? = null, val externalAccountId: String? = null,
    val username: String? = null, val capabilities: ChannelCapabilities? = null,
) {
    val listId: String get() = id ?: channel
}

@Serializable data class TemplateHeader(val format: String = "", val text: String = "", val parameters: List<String> = emptyList())

@Serializable
data class TemplateButton(
    val type: String = "", val text: String = "", val url: String = "", val phoneNumber: String = "", val example: String = "", val dynamic: Boolean = false,
)

@Serializable
data class Template(
    val id: String? = null, val name: String = "", val language: String = "", val category: String = "", val status: String = "",
    val parameterFormat: String = "POSITIONAL", val header: TemplateHeader? = null, val body: String = "", val footer: String = "",
    val buttons: List<TemplateButton> = emptyList(), val parameters: List<String> = emptyList(), val variables: Int = 0, val rejectedReason: String? = null,
) {
    val listId: String get() = "$name:$language"
}

@Serializable
data class DeviceRegistration(val token: String, val provider: String, val platform: String)

@Serializable
data class DeviceOut(val registered: Boolean = false, val provider: String = "")
