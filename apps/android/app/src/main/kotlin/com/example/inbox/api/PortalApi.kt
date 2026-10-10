package com.example.inbox.api

import java.net.URL
import java.net.URLEncoder
import kotlinx.serialization.Serializable
import kotlinx.serialization.builtins.ListSerializer

/** The portal endpoints the app calls, one function per route. */
object PortalApi {
    private fun enc(value: String) = ApiClient.encodePathComponent(value)
    private fun portal(session: Session, path: String) = ApiClient.portalPath(session, path)
    private fun q(value: String) = URLEncoder.encode(value, "UTF-8")
    /** Bodies whose null keys the server must see, such as clearing a team. */
    @OptIn(kotlinx.serialization.ExperimentalSerializationApi::class)
    private val explicit = kotlinx.serialization.json.Json(ApiClient.json) { explicitNulls = true }

    data class ConversationFilters(
        val status: ConversationStatus? = null,
        val mode: ConversationMode? = null,
        val assignee: String? = null,
        val team: String? = null,
        val unread: Boolean = false,
        val channel: String? = null,
        val search: String? = null,
        val limit: Int? = null,
        val offset: Int? = null,
    )

    /** Only advertised filters are sent; the server owns unread and assignment semantics. */
    fun conversationQuery(o: ConversationFilters): String {
        val items = ArrayList<String>()
        o.status?.let { items.add("status=${it.name.lowercase()}") }
        o.mode?.let { items.add("mode=${it.name.lowercase()}") }
        o.assignee?.takeIf { it.isNotEmpty() }?.let { items.add("assignee=${q(it)}") }
        o.team?.takeIf { it.isNotEmpty() }?.let { items.add("team=${q(it)}") }
        o.channel?.takeIf { it.isNotEmpty() }?.let { items.add("channel=${q(it)}") }
        o.search?.trim()?.takeIf { it.isNotEmpty() }?.let { items.add("search=${q(it)}") }
        if (o.unread) items.add("unread=true")
        o.limit?.let { items.add("limit=${it.coerceIn(1, 200)}") }
        o.offset?.let { items.add("offset=${it.coerceAtLeast(0)}") }
        return if (items.isEmpty()) "" else "?" + items.joinToString("&")
    }

    @Serializable
    private data class Credentials(val email: String, val password: String)

    suspend fun signIn(server: String, email: String, password: String): Session =
        ApiClient.request(server, "/mobile/sign-in", Session.serializer(), "POST", ApiClient.encode(Credentials(email, password)))

    /** Sign in by e-mail alone through the hosted service's directory. */
    suspend fun hostedSignIn(url: URL, email: String, password: String): List<HostedAccount> =
        ApiClient.request(url, HostedSignInResponse.serializer(), "POST", ApiClient.encode(Credentials(email, password))).accounts

    /** Re-checks a stored token on launch and refreshes branding the agency may have changed. */
    suspend fun resumeSession(server: String, token: String): Session =
        ApiClient.request(server, "/mobile/session", Session.serializer(), token = token)

    suspend fun listConversations(server: String, session: Session, filters: ConversationFilters): List<Conversation> =
        ApiClient.request(server, portal(session, "/conversations${conversationQuery(filters)}"), ListSerializer(Conversation.serializer()), token = session.token)

    suspend fun inboxSummary(server: String, session: Session): InboxSummary =
        ApiClient.request(server, portal(session, "/conversations/summary"), InboxSummary.serializer(), token = session.token)

    suspend fun conversation(server: String, session: Session, id: String): ConversationDetail =
        ApiClient.request(server, portal(session, "/conversations/${enc(id)}"), ConversationDetail.serializer(), token = session.token)

    private suspend fun change(server: String, session: Session, id: String, action: String, method: String, body: String): ConversationDetail =
        ApiClient.request(server, portal(session, "/conversations/${enc(id)}/$action"), ConversationDetail.serializer(), method, body, session.token)

    @Serializable private data class ModeBody(val mode: ConversationMode)
    @Serializable private data class StatusBody(val status: String)
    @Serializable private data class AssignBody(val assigneeId: String)
    @Serializable private data class TeamBody(val teamId: String?)
    @Serializable private data class ReplyBody(val content: String, val quotedMessageId: String?)
    @Serializable private data class ReactionBody(val emoji: String)
    @Serializable private data class AvailabilityBody(val availability: Availability)

    suspend fun setMode(server: String, session: Session, id: String, mode: ConversationMode) =
        change(server, session, id, "mode", "PATCH", ApiClient.encode(ModeBody(mode)))

    /** Resolved cases are final. New customer messages create another case. */
    suspend fun resolve(server: String, session: Session, id: String) =
        change(server, session, id, "status", "PATCH", ApiClient.encode(StatusBody("resolved")))

    suspend fun assign(server: String, session: Session, id: String, assigneeId: String) =
        change(server, session, id, "assignment", "POST", ApiClient.encode(AssignBody(assigneeId)))

    suspend fun setTeam(server: String, session: Session, id: String, teamId: String?) =
        change(server, session, id, "team", "PATCH", explicit.encodeToString(TeamBody.serializer(), TeamBody(teamId)))

    suspend fun markRead(server: String, session: Session, id: String) =
        ApiClient.requestVoid(server, portal(session, "/conversations/${enc(id)}/read"), "POST", token = session.token)

    suspend fun reply(server: String, session: Session, id: String, content: String, quotedMessageId: String?) =
        change(server, session, id, "reply", "POST", explicit.encodeToString(ReplyBody.serializer(), ReplyBody(content, quotedMessageId)))

    suspend fun replyWithFile(server: String, session: Session, id: String, file: OutgoingFile, caption: String): ConversationDetail =
        ApiClient.upload(server, portal(session, "/conversations/${enc(id)}/reply-media"), session.token, file, caption, ConversationDetail.serializer())

    suspend fun react(server: String, session: Session, id: String, messageId: String, emoji: String) =
        change(server, session, id, "messages/${enc(messageId)}/reaction", "POST", ApiClient.encode(ReactionBody(emoji)))

    /** Where an attachment can be fetched from, with the session's credentials. */
    fun attachmentUrl(server: String, session: Session, conversationId: String, attachmentId: String): String =
        "$server/api${portal(session, "/conversations/${enc(conversationId)}/attachments/${enc(attachmentId)}")}"

    suspend fun members(server: String, session: Session): List<PortalMember> =
        ApiClient.request(server, portal(session, "/members"), ListSerializer(PortalMember.serializer()), token = session.token)

    suspend fun teams(server: String, session: Session): List<Team> =
        ApiClient.request(server, portal(session, "/teams"), ListSerializer(Team.serializer()), token = session.token)

    suspend fun setAvailability(server: String, session: Session, availability: Availability): PortalMember =
        ApiClient.request(server, portal(session, "/me"), PortalMember.serializer(), "PATCH", ApiClient.encode(AvailabilityBody(availability)), session.token)

    suspend fun createTeam(server: String, session: Session, team: TeamUpdate): Team =
        ApiClient.request(server, portal(session, "/teams"), Team.serializer(), "POST", ApiClient.encode(team), session.token)

    suspend fun updateTeam(server: String, session: Session, id: String, team: TeamUpdate): Team =
        ApiClient.request(server, portal(session, "/teams/${enc(id)}"), Team.serializer(), "PATCH", ApiClient.encode(team), session.token)

    data class ReportFilters(val from: String, val to: String, val tzOffset: Int, val channel: String? = null, val teamId: String? = null)

    suspend fun report(server: String, session: Session, f: ReportFilters): PortalReport {
        val items = arrayListOf("from=${q(f.from)}", "to=${q(f.to)}", "tz_offset=${f.tzOffset}")
        f.channel?.takeIf { it.isNotEmpty() }?.let { items.add("channel=${q(it)}") }
        f.teamId?.takeIf { it.isNotEmpty() }?.let { items.add("team_id=${q(it)}") }
        return ApiClient.request(server, portal(session, "/reports?" + items.joinToString("&")), PortalReport.serializer(), token = session.token)
    }

    suspend fun channels(server: String, session: Session): List<PortalChannel> =
        ApiClient.request(server, portal(session, "/channels"), ListSerializer(PortalChannel.serializer()), token = session.token)

    suspend fun templates(server: String, session: Session): List<Template> =
        ApiClient.request(server, portal(session, "/templates"), ListSerializer(Template.serializer()), token = session.token)

    suspend fun deleteTemplate(server: String, session: Session, name: String) =
        ApiClient.requestVoid(server, portal(session, "/templates/${enc(name)}"), "DELETE", token = session.token)

    suspend fun cannedReplies(server: String, session: Session): List<CannedReply> =
        ApiClient.request(server, portal(session, "/canned-responses"), ListSerializer(CannedReply.serializer()), token = session.token)

    suspend fun createCannedReply(server: String, session: Session, reply: CannedReplyCreate): CannedReply =
        ApiClient.request(server, portal(session, "/canned-responses"), CannedReply.serializer(), "POST", ApiClient.encode(reply), session.token)

    suspend fun updateCannedReply(server: String, session: Session, id: String, reply: CannedReplyUpdate): CannedReply =
        ApiClient.request(server, portal(session, "/canned-responses/${enc(id)}"), CannedReply.serializer(), "PATCH", ApiClient.encode(reply), session.token)

    suspend fun deleteCannedReply(server: String, session: Session, id: String) =
        ApiClient.requestVoid(server, portal(session, "/canned-responses/${enc(id)}"), "DELETE", token = session.token)

    suspend fun tags(server: String, session: Session): List<ContactTag> =
        ApiClient.request(server, portal(session, "/tags"), ListSerializer(ContactTag.serializer()), token = session.token)

    suspend fun createTag(server: String, session: Session, tag: ContactTagCreate): ContactTag =
        ApiClient.request(server, portal(session, "/tags"), ContactTag.serializer(), "POST", ApiClient.encode(tag), session.token)

    suspend fun updateTag(server: String, session: Session, id: String, tag: ContactTagUpdate): ContactTag =
        ApiClient.request(server, portal(session, "/tags/${enc(id)}"), ContactTag.serializer(), "PATCH", ApiClient.encode(tag), session.token)

    suspend fun deleteTag(server: String, session: Session, id: String) =
        ApiClient.requestVoid(server, portal(session, "/tags/${enc(id)}"), "DELETE", token = session.token)

    /** Replace the contact's tags with the given set. */
    suspend fun setContactTags(server: String, session: Session, id: String, tagIds: List<String>): Contact =
        ApiClient.request(server, portal(session, "/contacts/${enc(id)}/tags"), Contact.serializer(), "PUT", ApiClient.encode(ContactTagsSet(tagIds)), session.token)

    suspend fun createContact(server: String, session: Session, contact: ContactCreate): Contact =
        ApiClient.request(server, portal(session, "/contacts"), Contact.serializer(), "POST", ApiClient.encode(contact), session.token)

    suspend fun updateContact(server: String, session: Session, id: String, contact: ContactUpdate): Contact =
        ApiClient.request(server, portal(session, "/contacts/${enc(id)}"), Contact.serializer(), "PATCH", contact.toJson(), session.token)

    /** Reaching out first on the bridge: a free text message that opens a case assigned to the sender. */
    suspend fun startWhatsAppConversation(server: String, session: Session, contactId: String, text: String): ConversationDetail =
        ApiClient.request(server, portal(session, "/contacts/${enc(contactId)}/conversations"), ConversationDetail.serializer(), "POST",
            ApiClient.json.encodeToString(StartText.serializer(), StartText("whatsapp", text)), session.token)

    @Serializable private data class StartText(val channel: String, val text: String)

    suspend fun contacts(server: String, session: Session, search: String?, limit: Int, offset: Int): List<Contact> =
        ApiClient.request(server, portal(session, "/contacts${conversationQuery(ConversationFilters(search = search, limit = limit, offset = offset))}"), ListSerializer(Contact.serializer()), token = session.token)

    suspend fun contact(server: String, session: Session, id: String): Contact =
        ApiClient.request(server, portal(session, "/contacts/${enc(id)}"), Contact.serializer(), token = session.token)

    suspend fun contactConversations(server: String, session: Session, id: String): List<Conversation> =
        ApiClient.request(server, portal(session, "/contacts/${enc(id)}/conversations"), ListSerializer(Conversation.serializer()), token = session.token)

    /** Tell the server where to reach this install. */
    suspend fun registerDevice(server: String, session: Session, device: DeviceRegistration): DeviceOut =
        ApiClient.request(server, "/mobile/devices", DeviceOut.serializer(), "POST", ApiClient.encode(device), session.token)

    /** Stop notifying this install, on sign-out. */
    suspend fun forgetDevice(server: String, session: Session, token: String) =
        ApiClient.requestVoid(server, "/mobile/devices/${enc(token)}", "DELETE", token = session.token)

    fun assetUrl(server: String, path: String?): String? {
        if (path.isNullOrEmpty()) return null
        return if (path.startsWith("http")) path else "$server$path"
    }
}
