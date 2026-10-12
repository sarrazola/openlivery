package com.example.inbox.rules

/** A push selects a record, never a server or authentication identity. */
object NotificationTarget {
    fun conversationId(data: Map<String, String>, clientId: String): String? {
        val flat = NotificationData.normalize(data)
        val id = (flat["conversation_id"] as? String)?.trim() ?: return null
        if (id.isEmpty() || id.length > 128) return null
        val client = flat["client_id"]
        if (client != null && (client !is String || client != clientId)) return null
        return id
    }
}
