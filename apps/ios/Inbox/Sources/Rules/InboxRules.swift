import Foundation

/// Rules shared by inbox lists and thread actions.
///
/// The server enforces all of them. They are mirrored here so the composer can
/// close itself between polling ticks, instead of offering a reply the server
/// is about to refuse.
enum InboxRules {
    static func isSocialChannel(_ channel: String) -> Bool { channel == "instagram" || channel == "messenger" }
    static func isWhatsApp(_ channel: String) -> Bool { channel == "whatsapp" || channel == "whatsapp_cloud" }

    private static func windowIsOpen(_ open: Bool?, _ until: String?, now: Date) -> Bool {
        guard open == true, let until = ISODate.parse(until) else { return false }
        return until > now
    }

    static func isReplyWindowClosed(_ c: ConversationDetail, now: Date = Date()) -> Bool {
        if isSocialChannel(c.channel) {
            if let reason = c.replyBlockReason, !reason.isEmpty { return true }
            return !windowIsOpen(c.humanReplyWindowOpen, c.humanReplyWindowUntil, now: now)
                && !windowIsOpen(c.replyWindowOpen, c.replyWindowUntil, now: now)
        }
        guard c.channel == "whatsapp_cloud" else { return false }
        if c.replyWindowOpen == false { return true }
        guard let until = ISODate.parse(c.replyWindowUntil) else { return false }
        return until <= now
    }

    static func canReply(_ c: ConversationDetail, now: Date = Date()) -> Bool {
        c.status != .resolved && c.mode == .human && !isReplyWindowClosed(c, now: now)
    }

    static func capabilities(_ c: ConversationDetail) -> ChannelCapabilities {
        if isSocialChannel(c.channel) { return c.channelCapabilities ?? ChannelCapabilities() }
        return (c.channelCapabilities ?? ChannelCapabilities()).merged(over: .everything)
    }

    static func acceptsAttachment(channel: String, capabilities: ChannelCapabilities, mime: String) -> Bool {
        let kind: Bool?
        var isFile = false
        if mime.hasPrefix("image/") { kind = capabilities.image }
        else if mime.hasPrefix("audio/") { kind = capabilities.audio }
        else if mime.hasPrefix("video/") { kind = capabilities.video }
        else { kind = capabilities.file; isFile = true }
        return kind == true && !(channel == "instagram" && isFile && mime != "application/pdf")
    }

    /// The approved human window is open but the automated one is not.
    static func humanWindowOnly(_ c: ConversationDetail, now: Date = Date()) -> Bool {
        isSocialChannel(c.channel) && !isReplyWindowClosed(c, now: now)
            && !windowIsOpen(c.replyWindowOpen, c.replyWindowUntil, now: now)
    }

    struct Delivery { let label: String; let symbol: String }

    static func delivery(_ status: String?) -> Delivery? {
        guard let status, !status.isEmpty else { return nil }
        switch status {
        case "read", "delivered": return Delivery(label: status, symbol: "checkmark.circle")
        case "sent": return Delivery(label: "sent", symbol: "checkmark")
        case "failed": return Delivery(label: "failed", symbol: "exclamationmark.circle")
        case "pending": return Delivery(label: "pending", symbol: "clock")
        default: return Delivery(label: "unknown", symbol: "questionmark.circle")
        }
    }

    static func canQuote(_ c: ConversationDetail, _ message: Message, now: Date = Date()) -> Bool {
        canReply(c, now: now) && c.channelCapabilities?.quotes != false && isWhatsApp(c.channel)
            && !message.isActivity && message.role != "system"
    }

    static func canReact(_ c: ConversationDetail, _ message: Message) -> Bool {
        // Reactions are separate from free-form messages and do not use the 24h window.
        c.status != .resolved && c.mode == .human && c.channelCapabilities?.reactions != false && isWhatsApp(c.channel)
            && !message.isActivity && message.role == "user"
    }

    /// The same placeholders the web fills: the contact's details and the operator's name.
    /// `my_name` stays as an alias so replies saved before the rename keep resolving.
    struct CannedVariables { var contactName: String; var contactPhone: String; var contactEmail: String; var agentName: String }

    static func interpolate(_ content: String, _ variables: CannedVariables) -> String {
        let values = [
            "contact_name": variables.contactName, "contact_phone": variables.contactPhone,
            "contact_email": variables.contactEmail, "agent_name": variables.agentName, "my_name": variables.agentName,
        ]
        var result = content
        // Unknown or empty values stay visible so the operator notices and edits before sending.
        for (key, value) in values where !value.isEmpty { result = result.replacingOccurrences(of: "{\(key)}", with: value) }
        return result
    }

    /// A row's time follows the customer's message, never an operator action.
    static func timestamp(_ c: Conversation) -> String {
        [c.lastInboundAt, c.createdAt, c.updatedAt].compactMap { $0 }.first { !$0.isEmpty } ?? ""
    }

    /// Offset pagination can overlap when inbound messages move existing rows.
    static func mergePages(_ previous: [Conversation], _ incoming: [Conversation]) -> [Conversation] {
        var order: [String] = []
        var byId: [String: Conversation] = [:]
        for row in previous + incoming {
            if byId[row.id] == nil { order.append(row.id) }
            byId[row.id] = row
        }
        return order.compactMap { byId[$0] }
    }
}
