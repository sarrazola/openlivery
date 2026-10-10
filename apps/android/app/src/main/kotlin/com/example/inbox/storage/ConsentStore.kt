package com.example.inbox.storage

import android.content.Context
import com.example.inbox.api.Session
import java.net.URI

/**
 * Permission is specific to the account, workspace and disclosed processing.
 *
 * What is stored is a fingerprint of the disclosure the person accepted. A new
 * destination, a new disclosure version, another workspace or another account
 * all produce a different fingerprint, so the screen is shown again.
 */
object ConsentStore {
    private const val KEY = "inbox.privacy.v1"

    class MissingDisclosure : Exception()

    fun fingerprint(server: String, session: Session): String? {
        val privacy = session.privacy ?: return null
        if (privacy.version.isEmpty()) return null
        val kinds = setOf("ai", "integration", "notification")
        if (!privacy.destinations.all { it.kind in kinds }) return null
        val url = runCatching { URI(server) }.getOrNull() ?: return null
        val scheme = url.scheme ?: return null
        if (scheme !in listOf("http", "https") || url.userInfo != null) return null
        val host = url.host ?: return null
        var path = url.path ?: ""
        while (path.endsWith("/")) path = path.dropLast(1)
        val port = if (url.port >= 0) ":${url.port}" else ""
        val origin = "$scheme://$host$port$path"
        val destinations = privacy.destinations
            .map { d -> "${d.kind}|${d.name}|${d.host}|${d.capabilities.sorted().joinToString(",")}" }
            .sorted()
            .joinToString(";")
        return listOf(
            "policy=1", "server=$origin", "client=${session.clientId}", "user=${session.userId ?: "legacy"}",
            "version=${privacy.version}", "destinations=$destinations",
        ).joinToString("\n")
    }

    fun hasConsent(context: Context, server: String, session: Session): Boolean {
        val expected = fingerprint(server, session) ?: return false
        return SecureStore.open(context).getString(KEY, null) == expected
    }

    fun accept(context: Context, server: String, session: Session) {
        val value = fingerprint(server, session) ?: throw MissingDisclosure()
        SecureStore.open(context).edit().putString(KEY, value).commit()
    }

    fun withdraw(context: Context) {
        SecureStore.open(context).edit().remove(KEY).commit()
    }
}
