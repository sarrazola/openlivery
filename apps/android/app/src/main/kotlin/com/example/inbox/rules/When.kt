package com.example.inbox.rules

import com.example.inbox.localization.Strings
import java.time.Instant
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.ZoneId
import java.time.ZoneOffset
import java.time.format.DateTimeFormatter
import java.time.format.FormatStyle
import java.util.Locale

/** The server's timestamps: ISO 8601 with or without fraction or zone. */
object IsoDate {
    private val naive = DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss[.SSSSSS][.SSS]", Locale.ROOT)

    fun parse(value: String?): Instant? {
        if (value.isNullOrEmpty()) return null
        runCatching { return Instant.parse(value) }
        runCatching { return java.time.OffsetDateTime.parse(value).toInstant() }
        return runCatching { LocalDateTime.parse(value, naive).toInstant(ZoneOffset.UTC) }.getOrNull()
    }
}

/** Dates as the rows and bubbles show them. */
object When {
    private val zone: ZoneId get() = ZoneId.systemDefault()
    private val timeFormat: DateTimeFormatter get() = DateTimeFormatter.ofLocalizedTime(FormatStyle.SHORT).withLocale(Locale.getDefault())
    private val dayMonth: DateTimeFormatter get() = DateTimeFormatter.ofPattern("d MMM", Locale.getDefault())
    private val dayMonthWide: DateTimeFormatter get() = DateTimeFormatter.ofPattern("d MMMM", Locale.getDefault())
    private val dayMonthYear: DateTimeFormatter get() = DateTimeFormatter.ofPattern("d MMMM yyyy", Locale.getDefault())

    private fun local(iso: String): LocalDateTime? = IsoDate.parse(iso)?.atZone(zone)?.toLocalDateTime()

    fun time(iso: String): String = local(iso)?.format(timeFormat) ?: ""

    fun rowLabel(iso: String): String {
        val date = local(iso) ?: return ""
        val today = LocalDate.now(zone)
        return when (date.toLocalDate()) {
            today -> date.format(timeFormat)
            today.minusDays(1) -> Strings.current.`when`.yesterday
            else -> date.format(dayMonth)
        }
    }

    fun dayLabel(iso: String): String {
        val date = local(iso) ?: return ""
        val today = LocalDate.now(zone)
        return when {
            date.toLocalDate() == today -> Strings.current.`when`.today
            date.toLocalDate() == today.minusDays(1) -> Strings.current.`when`.yesterday
            date.year != today.year -> date.format(dayMonthYear)
            else -> date.format(dayMonthWide)
        }
    }

    fun shortDate(iso: String): String = local(iso)?.format(DateTimeFormatter.ofLocalizedDate(FormatStyle.SHORT).withLocale(Locale.getDefault())) ?: ""

    fun sameDay(a: String, b: String): Boolean {
        val first = local(a) ?: return false
        val second = local(b) ?: return false
        return first.toLocalDate() == second.toLocalDate()
    }
}
