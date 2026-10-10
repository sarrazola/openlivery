package com.example.inbox.localization

import java.util.Locale

/**
 * English and Spanish, chosen by the phone.
 *
 * There is no language picker on purpose: someone answering their business's
 * messages should not have to set one, and the phone already knows. Anything
 * the device is not set to falls back to English.
 */
object AppLocale {
    val languageCode: String get() = if (Locale.getDefault().language.lowercase() == "es") "es" else "en"
    val isSpanish: Boolean get() = languageCode == "es"
    fun <T> pick(en: T, es: T): T = if (isSpanish) es else en
}
