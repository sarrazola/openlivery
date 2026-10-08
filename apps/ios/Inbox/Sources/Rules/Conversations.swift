import Foundation

/// What to call a conversation.
///
/// The title the server stores is the first thing the customer typed, which is
/// fine as a database label and wrong as a name. So the name is the person, the
/// way it is in any messaging app, and when nobody gave a name, the next most
/// identifying thing the channel knows.
enum Conversations {
    /// `573001234567@s.whatsapp.net` -> `+573001234567`.
    static func phone(from externalChatId: String?) -> String? {
        let address = externalChatId ?? ""
        // Group and linked-device identifiers are not telephone numbers.
        if address.range(of: "@(?:g\\.us|lid)$", options: .regularExpression) != nil { return nil }
        let local = address.split(separator: "@", maxSplits: 1).first.map(String.init) ?? ""
        let beforeColon = local.split(separator: ":", maxSplits: 1).first.map(String.init) ?? ""
        let digits = beforeColon.filter(\.isNumber)
        // Short enough to be a group id or a placeholder rather than a number.
        return digits.count >= 7 ? "+\(digits)" : nil
    }

    static func channelLabel(_ channel: String) -> String {
        let s = Strings.current.channels
        if InboxRules.isWhatsApp(channel) { return s.whatsapp }
        switch channel {
        case "widget": return s.widget
        case "playground": return s.playground
        case "instagram": return s.instagram
        case "messenger": return s.messenger
        default: return channel
        }
    }

    /// A longer label where WhatsApp Business is distinguished from the bridge.
    static func channelName(_ channel: String) -> String {
        switch channel {
        case "whatsapp_cloud": return "WhatsApp Business"
        case "whatsapp": return "WhatsApp"
        case "instagram": return "Instagram"
        case "messenger": return "Facebook Messenger"
        case "widget": return WorkspaceStrings.current.web
        default: return channel
        }
    }

    /// SF Symbols stand in for the brand glyphs the web uses.
    static func channelSymbol(_ channel: String) -> String {
        if InboxRules.isWhatsApp(channel) { return "phone.bubble" }
        switch channel {
        case "instagram": return "camera"
        case "messenger": return "bubble.left.and.bubble.right"
        case "playground": return "flask"
        default: return "globe"
        }
    }

    /// Who this conversation is with.
    static func name(_ c: Conversation) -> String {
        let named = (c.contactName ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        if !named.isEmpty { return named }
        if InboxRules.isWhatsApp(c.channel), let phone = phone(from: c.externalChatId) { return phone }
        if c.channel == "widget" { return Strings.current.list.webVisitor }
        let title = c.title.trimmingCharacters(in: .whitespacesAndNewlines)
        return title.isEmpty ? Strings.current.list.untitled : title
    }

    static func name(_ c: ConversationDetail) -> String { name(c.summary) }

    /// The letter shown in the avatar when there is no picture.
    static func initial(_ name: String) -> String {
        var value = name.trimmingCharacters(in: .whitespacesAndNewlines)
        if value.hasPrefix("+") { value.removeFirst() }
        value = value.trimmingCharacters(in: .whitespaces)
        guard let first = value.first else { return "?" }
        return String(first).uppercased()
    }
}

/// Dates as the rows and bubbles show them.
enum When {
    static func time(_ iso: String) -> String {
        guard let date = ISODate.parse(iso) else { return "" }
        return date.formatted(date: .omitted, time: .shortened)
    }

    static func rowLabel(_ iso: String) -> String {
        guard let date = ISODate.parse(iso) else { return "" }
        let calendar = Calendar.current
        if calendar.isDateInToday(date) { return date.formatted(date: .omitted, time: .shortened) }
        if calendar.isDateInYesterday(date) { return Strings.current.when.yesterday }
        return date.formatted(.dateTime.day().month(.abbreviated))
    }

    static func dayLabel(_ iso: String) -> String {
        guard let date = ISODate.parse(iso) else { return "" }
        let calendar = Calendar.current
        if calendar.isDateInToday(date) { return Strings.current.when.today }
        if calendar.isDateInYesterday(date) { return Strings.current.when.yesterday }
        if calendar.component(.year, from: date) != calendar.component(.year, from: Date()) {
            return date.formatted(.dateTime.day().month(.wide).year())
        }
        return date.formatted(.dateTime.day().month(.wide))
    }

    static func shortDate(_ iso: String) -> String {
        guard let date = ISODate.parse(iso) else { return "" }
        return date.formatted(date: .numeric, time: .omitted)
    }

    static func sameDay(_ a: String, _ b: String) -> Bool {
        guard let first = ISODate.parse(a), let second = ISODate.parse(b) else { return false }
        return Calendar.current.isDate(first, inSameDayAs: second)
    }
}
