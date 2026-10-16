package com.example.inbox

import java.net.URL

/**
 * The identity this build was compiled with.
 *
 * `brand/brand.properties` is read by Gradle at build time and its values land
 * in `BuildConfig`. Nothing here is fetched or configurable at runtime: an
 * app's identity is decided when it is built.
 */
object Brand {
    private fun value(raw: String): String = raw.trim()

    /** Addresses in the brand file carry no scheme. */
    private fun httpsUrl(raw: String): URL? {
        val trimmed = raw.trim()
        if (trimmed.isEmpty()) return null
        val candidate = if (trimmed.contains("://")) trimmed else "https://$trimmed"
        val url = runCatching { URL(candidate) }.getOrNull() ?: return null
        if (url.protocol != "https" || url.host.isNullOrEmpty() || url.userInfo != null) return null
        return url
    }

    val name: String = value(BuildConfig.BRAND_PRODUCT_NAME).ifEmpty { "Inbox" }

    /** Only the sign-in screen uses it; the workspace's own colour arrives with the session. */
    val primaryColorHex: String = value(BuildConfig.BRAND_PRIMARY_COLOR).replace("#", "").let { if (it.length == 6) "#$it" else com.example.inbox.ui.Theme.defaultBrand }

    val defaultServer: String = httpsUrl(value(BuildConfig.BRAND_DEFAULT_SERVER))?.toString() ?: ""

    /**
     * A preset for a service whoever published this build runs.
     *
     * There is none in this repository, on purpose: an open-source build should
     * not point at somebody's hosted product. A build that has one offers it as a
     * choice alongside typing an address.
     */
    data class HostedPreset(val label: String, val serverTemplate: String)

    val hosted: HostedPreset? = run {
        val label = value(BuildConfig.BRAND_HOSTED_LABEL)
        val template = value(BuildConfig.BRAND_HOSTED_SERVER_TEMPLATE)
        if (label.isEmpty() || !template.contains("{workspace}")) return@run null
        val withScheme = if (template.contains("://")) template else "https://$template"
        if (!withScheme.startsWith("https://")) null else HostedPreset(label, withScheme)
    }

    /** Optional account-directory endpoint used by a configured service preset. */
    val hostedSignInUrl: URL? = run {
        if (hosted == null) return@run null
        val raw = value(BuildConfig.BRAND_HOSTED_SIGN_IN)
        if (raw.isEmpty()) return@run null
        // Plain HTTP only for a development server on the local network.
        val normalized = com.example.inbox.api.ApiClient.normalizeServerUrl(raw)
        if (normalized.startsWith("http://")) runCatching { URL(normalized) }.getOrNull() else httpsUrl(raw)
    }

    /** Turn what someone typed into the address their workspace lives at. */
    fun hostedServer(workspace: String): String {
        val preset = hosted ?: return ""
        return HostedServer.resolve(workspace, preset.serverTemplate) ?: ""
    }

    private fun localized(en: String, es: String): URL? {
        val preferred = if (com.example.inbox.localization.AppLocale.isSpanish) es else en
        return httpsUrl(preferred.ifEmpty { en })
    }

    val privacyPolicyUrl: URL? get() = localized(BuildConfig.BRAND_PRIVACY_POLICY_URL_EN, BuildConfig.BRAND_PRIVACY_POLICY_URL_ES)
    val supportUrl: URL? get() = localized(BuildConfig.BRAND_SUPPORT_URL_EN, BuildConfig.BRAND_SUPPORT_URL_ES)
}
