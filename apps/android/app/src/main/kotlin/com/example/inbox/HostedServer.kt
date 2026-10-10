package com.example.inbox

import java.net.URI

/** Resolve only workspace names or addresses belonging to the configured service. */
object HostedServer {
    private val validName = Regex("^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")

    fun resolve(input: String, template: String): String? {
        val value = input.trim().lowercase()
        if (!template.contains("{workspace}") || value.isEmpty()) return null
        if (validName.matches(value)) return template.replace("{workspace}", value)
        val address = runCatching { URI(if (value.contains("://")) value else "https://$value") }.getOrNull() ?: return null
        val sample = runCatching { URI(template.replace("{workspace}", "workspace-placeholder")) }.getOrNull() ?: return null
        val addressHost = address.host ?: return null
        val sampleHost = sample.host ?: return null
        val parts = sampleHost.split("workspace-placeholder")
        if (parts.size != 2) return null
        val (prefix, suffix) = parts
        if (address.scheme != "https" || sample.scheme != "https" || address.userInfo != null || address.query != null || address.fragment != null) return null
        if (address.port != sample.port || normalizedPath(address) != normalizedPath(sample)) return null
        if (!addressHost.startsWith(prefix) || !addressHost.endsWith(suffix) || addressHost.length < prefix.length + suffix.length) return null
        val name = addressHost.substring(prefix.length, addressHost.length - suffix.length)
        return if (validName.matches(name)) template.replace("{workspace}", name) else null
    }

    private fun normalizedPath(uri: URI): String = uri.path.ifEmpty { "/" }
}
