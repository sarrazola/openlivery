import Foundation

enum Reports {
    private static func localISO(_ date: Date) -> String {
        let parts = Calendar.current.dateComponents([.year, .month, .day], from: date)
        return String(format: "%04d-%02d-%02d", parts.year ?? 0, parts.month ?? 0, parts.day ?? 0)
    }

    /// The API groups local days using JavaScript's positive-west offset.
    static func range(days: Int, today: Date = Date()) -> PortalAPI.ReportFilters {
        let start = Calendar.current.date(byAdding: .day, value: -(days - 1), to: today) ?? today
        return range(from: start, to: today)
    }

    /// Any two local days, oldest first; the API accepts up to a year.
    static func range(from: Date, to: Date) -> PortalAPI.ReportFilters {
        let (first, last) = from <= to ? (from, to) : (to, from)
        let offsetMinutes = -TimeZone.current.secondsFromGMT(for: last) / 60
        return PortalAPI.ReportFilters(from: localISO(first), to: localISO(last), tzOffset: offsetMinutes)
    }

    static func spanDays(_ filters: PortalAPI.ReportFilters) -> Int {
        guard let a = date(filters.from), let b = date(filters.to) else { return 7 }
        return (Calendar.current.dateComponents([.day], from: a, to: b).day ?? 0) + 1
    }

    static func duration(_ seconds: Double?, _ s: WorkspaceStrings) -> String {
        guard let seconds, seconds.isFinite else { return s.noData }
        let value = max(0, Int(seconds.rounded()))
        if value < 60 { return "\(value) \(s.seconds)" }
        let minutes = Int((Double(value) / 60).rounded())
        if minutes < 60 { return "\(minutes) \(s.minutes)" }
        let hours = minutes / 60
        let rest = minutes % 60
        return rest > 0 ? "\(hours) \(s.hours) \(rest) \(s.minutes)" : "\(hours) \(s.hours)"
    }

    /// `UTC-05:00` for the zone the days were grouped in.
    static func utcLabel(tzOffset: Int) -> String {
        let minutes = -tzOffset
        let sign = minutes >= 0 ? "+" : "-"
        return String(format: "UTC%@%02d:%02d", sign, abs(minutes) / 60, abs(minutes) % 60)
    }

    private static let dayFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.dateFormat = "yyyy-MM-dd"
        return formatter
    }()

    static func date(_ isoDay: String) -> Date? { dayFormatter.date(from: isoDay) }

    static func dayLabel(_ isoDay: String) -> String {
        guard let date = date(isoDay) else { return isoDay }
        return date.formatted(.dateTime.day().month(.abbreviated))
    }
}
