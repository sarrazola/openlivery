package com.example.inbox.rules

import com.example.inbox.api.PortalApi
import com.example.inbox.localization.WorkspaceStrings
import java.time.LocalDate
import java.time.ZoneId
import java.time.ZonedDateTime
import java.time.format.DateTimeFormatter
import java.time.temporal.ChronoUnit
import java.util.Locale
import kotlin.math.abs
import kotlin.math.roundToInt

object Reports {
    private val isoDay: DateTimeFormatter = DateTimeFormatter.ofPattern("yyyy-MM-dd", Locale.ROOT)

    /** The API groups local days using JavaScript's positive-west offset. */
    fun range(days: Int, today: LocalDate = LocalDate.now()): PortalApi.ReportFilters = range(today.minusDays((days - 1).toLong()), today)

    fun range(from: LocalDate, to: LocalDate): PortalApi.ReportFilters {
        val (first, last) = if (from <= to) from to to else to to from
        val offsetSeconds = ZonedDateTime.of(last.atStartOfDay(), ZoneId.systemDefault()).offset.totalSeconds
        return PortalApi.ReportFilters(first.format(isoDay), last.format(isoDay), -offsetSeconds / 60)
    }

    fun spanDays(filters: PortalApi.ReportFilters): Int {
        val a = date(filters.from) ?: return 7
        val b = date(filters.to) ?: return 7
        return ChronoUnit.DAYS.between(a, b).toInt() + 1
    }

    fun duration(seconds: Double?, s: WorkspaceStrings): String {
        if (seconds == null || !seconds.isFinite()) return s.noData
        val value = maxOf(0, seconds.roundToInt())
        if (value < 60) return "$value ${s.seconds}"
        val minutes = (value / 60.0).roundToInt()
        if (minutes < 60) return "$minutes ${s.minutes}"
        val hours = minutes / 60
        val rest = minutes % 60
        return if (rest > 0) "$hours ${s.hours} $rest ${s.minutes}" else "$hours ${s.hours}"
    }

    /** `UTC-05:00` for the zone the days were grouped in. */
    fun utcLabel(tzOffset: Int): String {
        val minutes = -tzOffset
        val sign = if (minutes >= 0) "+" else "-"
        return String.format(Locale.ROOT, "UTC%s%02d:%02d", sign, abs(minutes) / 60, abs(minutes) % 60)
    }

    fun date(isoDayValue: String): LocalDate? = runCatching { LocalDate.parse(isoDayValue, isoDay) }.getOrNull()

    fun dayLabel(isoDayValue: String): String = date(isoDayValue)?.format(DateTimeFormatter.ofPattern("d MMM", Locale.getDefault())) ?: isoDayValue
}
