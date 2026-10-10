package com.example.inbox

import com.example.inbox.api.ApiClient
import com.example.inbox.api.Conversation
import com.example.inbox.api.ConversationDetail
import com.example.inbox.api.ConversationMode
import com.example.inbox.api.ConversationStatus
import com.example.inbox.api.Message
import com.example.inbox.localization.ChatStrings
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import com.example.inbox.rules.Conversations
import com.example.inbox.rules.InboxRules
import com.example.inbox.rules.IsoDate
import java.time.Instant
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class RulesTest {
    @Test
    fun hostedServerAcceptsNameOrMatchingAddress() {
        val template = "https://{workspace}.example.com"
        assertEquals("https://acme.example.com", HostedServer.resolve("Acme", template))
        assertEquals("https://acme.example.com", HostedServer.resolve("https://acme.example.com", template))
        assertNull(HostedServer.resolve("https://acme.other.com", template))
        assertNull(HostedServer.resolve("https://acme.example.com/path", template))
        assertNull(HostedServer.resolve("bad name", template))
    }

    @Test
    fun serverNormalization() {
        assertEquals("https://example.com", ApiClient.normalizeServerUrl("example.com/"))
        assertEquals("http://10.0.0.4:8000", ApiClient.normalizeServerUrl("10.0.0.4:8000"))
        assertEquals("http://10.0.2.2:3000", ApiClient.normalizeServerUrl("10.0.2.2:3000"))
        assertEquals("https://chat.example.com", ApiClient.normalizeServerUrl("https://chat.example.com/api"))
        assertEquals("", ApiClient.normalizeServerUrl("   "))
    }

    @Test
    fun phoneFromWhatsAppAddress() {
        assertEquals("+573001234567", Conversations.phone("573001234567@s.whatsapp.net"))
        assertNull(Conversations.phone("120363@g.us"))
        assertNull(Conversations.phone("12345@s.whatsapp.net"))
        assertEquals("5", Conversations.initial("+573001234567"))
        assertEquals("A", Conversations.initial("  ana"))
        assertEquals("?", Conversations.initial(""))
    }

    @Test
    fun isoDatesWithAndWithoutZone() {
        assertNotNull(IsoDate.parse("2026-01-01T10:00:00Z"))
        assertNotNull(IsoDate.parse("2026-01-01T10:00:00.123456Z"))
        assertNotNull(IsoDate.parse("2026-01-01T10:00:00+02:00"))
        assertNotNull(IsoDate.parse("2026-01-01T10:00:00.123456"))
        assertNotNull(IsoDate.parse("2026-01-01T10:00:00"))
        assertNull(IsoDate.parse(""))
    }

    private fun detail(channel: String, open: Boolean, until: String?, mode: ConversationMode = ConversationMode.HUMAN) =
        ConversationDetail.opening(Conversation(id = "c", channel = channel, mode = mode, replyWindowOpen = open, replyWindowUntil = until, createdAt = "2026-01-01T00:00:00Z", updatedAt = "2026-01-01T00:00:00Z"))

    @Test
    fun replyWindowRules() {
        val now = Instant.parse("2026-01-01T12:00:00Z")
        assertTrue(InboxRules.canReply(detail("whatsapp", true, null), now))
        assertTrue(InboxRules.canReply(detail("whatsapp_cloud", true, "2026-01-01T13:00:00Z"), now))
        assertFalse(InboxRules.canReply(detail("whatsapp_cloud", true, "2026-01-01T11:00:00Z"), now))
        assertFalse(InboxRules.canReply(detail("whatsapp_cloud", false, null), now))
        assertFalse(InboxRules.canReply(detail("widget", true, null, ConversationMode.AI), now))
        val resolved = detail("widget", true, null).copy(status = ConversationStatus.RESOLVED)
        assertFalse(InboxRules.canReply(resolved, now))
    }

    @Test
    fun cannedInterpolationLeavesUnknownKeys() {
        val vars = InboxRules.CannedVariables("Ana", "+57300", "", "Juan")
        assertEquals("Hi Ana, {unknown}", InboxRules.interpolate("Hi {contact_name}, {unknown}", vars))
        assertEquals("Juan / Juan / +57300 / {contact_email}", InboxRules.interpolate("{agent_name} / {my_name} / {contact_phone} / {contact_email}", vars))
    }

    @Test
    fun mergePagesKeepsOrderAndReplacesRows() {
        val a = Conversation(id = "a", preview = "old")
        val b = Conversation(id = "b")
        val merged = InboxRules.mergePages(listOf(a, b), listOf(Conversation(id = "a", preview = "new"), Conversation(id = "c")))
        assertEquals(listOf("a", "b", "c"), merged.map { it.id })
        assertEquals("new", merged[0].preview)
    }

    @Test
    fun activityLabelFillsTheActorAndVariables() {
        val resolved = Message(id = "m1", kind = "activity", senderName = "Ana", activity = JsonObject(mapOf("event" to JsonPrimitive("resolved"))))
        assertEquals("Ana resolved the conversation", ChatStrings.en.activityLabel(resolved))
        val auto = Message(id = "m2", kind = "activity", content = "fallback", activity = JsonObject(mapOf("event" to JsonPrimitive("auto_resolved"), "hours" to JsonPrimitive(24))))
        assertEquals("Resolved automatically after 24 h without activity", ChatStrings.en.activityLabel(auto))
        val unknown = Message(id = "m3", kind = "activity", content = "fallback", activity = JsonObject(mapOf("event" to JsonPrimitive("something_else"))))
        assertEquals("fallback", ChatStrings.en.activityLabel(unknown))
    }
}
