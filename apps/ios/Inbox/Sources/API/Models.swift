import Foundation

/// What the portal API returns. Keys arrive in snake_case and are decoded with
/// `.convertFromSnakeCase`, so property names here are the camelCase spelling.

struct Branding: Codable, Equatable {
    var agencyName: String
    var clientName: String
    var portalTitle: String
    var brandColor: String
    var agencyLogoUrl: String?
    var clientLogoUrl: String?
}

/// How the server this app is pointed at expects to be able to notify it.
///
/// The app deliberately does not decide this. One build has to work against a
/// self-hosted server that sends nothing and a hosted one that does, and a phone
/// that subscribes to a push service nobody asked for costs whoever owns that
/// service money. So the server says, and `enabled: false` means do not
/// initialise anything at all.
struct PushConfig: Codable, Equatable {
    var enabled: Bool
    var provider: String
}

struct PrivacyDestination: Codable, Equatable {
    var kind: String
    var name: String
    var host: String
    var capabilities: [String]
}

struct PrivacyDisclosure: Codable, Equatable {
    var version: String
    var destinations: [PrivacyDestination]
}

struct Session: Codable, Equatable {
    var token: String
    var portalSlug: String
    var clientId: String
    var userId: String?
    var userName: String
    var role: String?
    var permissions: [String]?
    var branding: Branding
    var push: PushConfig
    var apiVersion: Int
    var privacy: PrivacyDisclosure?
}

struct Attachment: Codable, Equatable, Identifiable {
    var id: String
    var kind: String
    var mime: String
    var filename: String?
    var sizeBytes: Int
}

enum ConversationMode: String, Codable { case ai, human }
enum ConversationStatus: String, Codable { case open, resolved }
enum Availability: String, Codable { case online, away }

/// Social channels advertise what they accept; WhatsApp and the widget accept everything.
struct ChannelCapabilities: Codable, Hashable {
    var text: Bool?
    var image: Bool?
    var audio: Bool?
    var video: Bool?
    var file: Bool?
    var quotes: Bool?
    var reactions: Bool?
    var templates: Bool?

    static let everything = ChannelCapabilities(text: true, image: true, audio: true, video: true, file: true)

    /// Defaults fill the gaps a channel leaves unstated.
    func merged(over defaults: ChannelCapabilities) -> ChannelCapabilities {
        ChannelCapabilities(
            text: text ?? defaults.text, image: image ?? defaults.image, audio: audio ?? defaults.audio,
            video: video ?? defaults.video, file: file ?? defaults.file, quotes: quotes ?? defaults.quotes,
            reactions: reactions ?? defaults.reactions, templates: templates ?? defaults.templates
        )
    }
}

struct Message: Codable, Equatable, Identifiable {
    var id: String
    var role: String
    var kind: String
    var activity: [String: JSONValue]?
    var content: String
    var senderType: String
    var senderName: String?
    var externalMessageId: String?
    var deliveryStatus: String?
    var deliveryError: String?
    var reaction: String?
    var incomingReaction: String?
    var quotedMessageId: String?
    var createdAt: String
    var attachments: [Attachment]

    var isActivity: Bool { kind == "activity" }
    var isOutgoing: Bool { role == "assistant" }
    var isAI: Bool { isOutgoing && senderType == "ai" }
}

struct Conversation: Codable, Hashable, Identifiable {
    var id: String
    var clientId: String
    var agentId: String
    var title: String
    var mode: ConversationMode
    var status: ConversationStatus
    var channel: String
    var externalChatId: String?
    var contactName: String?
    var contactId: String?
    var contactEmail: String?
    var preview: String
    var unread: Bool
    var unreadCount: Int
    var assigneeId: String?
    var assigneeName: String?
    var teamId: String?
    var teamName: String?
    var replyWindowUntil: String?
    var replyWindowOpen: Bool
    var humanReplyWindowOpen: Bool?
    var humanReplyWindowUntil: String?
    var replyBlockReason: String?
    var socialChannelId: String?
    var channelCapabilities: ChannelCapabilities?
    var lastInboundAt: String?
    var resolvedAt: String?
    var firstReplyAt: String?
    var takenOverAt: String?
    var waitingSince: String?
    var createdAt: String
    var updatedAt: String
}

struct ConversationDetail: Codable, Equatable, Identifiable {
    var id: String
    var clientId: String
    var agentId: String
    var title: String
    var mode: ConversationMode
    var status: ConversationStatus
    var channel: String
    var externalChatId: String?
    var contactName: String?
    var contactId: String?
    var contactEmail: String?
    var preview: String
    var unread: Bool
    var unreadCount: Int
    var assigneeId: String?
    var assigneeName: String?
    var teamId: String?
    var teamName: String?
    var replyWindowUntil: String?
    var replyWindowOpen: Bool
    var humanReplyWindowOpen: Bool?
    var humanReplyWindowUntil: String?
    var replyBlockReason: String?
    var socialChannelId: String?
    var channelCapabilities: ChannelCapabilities?
    var lastInboundAt: String?
    var resolvedAt: String?
    var firstReplyAt: String?
    var takenOverAt: String?
    var waitingSince: String?
    var createdAt: String
    var updatedAt: String
    var messages: [Message]

    /// The list row shape, for everything that reasons about a conversation without its messages.
    var summary: Conversation {
        Conversation(
            id: id, clientId: clientId, agentId: agentId, title: title, mode: mode, status: status, channel: channel,
            externalChatId: externalChatId, contactName: contactName, contactId: contactId, contactEmail: contactEmail, preview: preview, unread: unread,
            unreadCount: unreadCount, assigneeId: assigneeId, assigneeName: assigneeName, teamId: teamId, teamName: teamName,
            replyWindowUntil: replyWindowUntil, replyWindowOpen: replyWindowOpen, humanReplyWindowOpen: humanReplyWindowOpen,
            humanReplyWindowUntil: humanReplyWindowUntil, replyBlockReason: replyBlockReason, socialChannelId: socialChannelId,
            channelCapabilities: channelCapabilities, lastInboundAt: lastInboundAt, resolvedAt: resolvedAt, firstReplyAt: firstReplyAt,
            takenOverAt: takenOverAt, waitingSince: waitingSince, createdAt: createdAt, updatedAt: updatedAt
        )
    }

    /// A row opened from the list, before its messages have loaded.
    init(opening conversation: Conversation) {
        id = conversation.id; clientId = conversation.clientId; agentId = conversation.agentId; title = conversation.title
        mode = conversation.mode; status = conversation.status; channel = conversation.channel; externalChatId = conversation.externalChatId
        contactName = conversation.contactName; contactId = conversation.contactId; contactEmail = conversation.contactEmail; preview = conversation.preview; unread = conversation.unread
        unreadCount = conversation.unreadCount; assigneeId = conversation.assigneeId; assigneeName = conversation.assigneeName
        teamId = conversation.teamId; teamName = conversation.teamName; replyWindowUntil = conversation.replyWindowUntil
        replyWindowOpen = conversation.replyWindowOpen; humanReplyWindowOpen = conversation.humanReplyWindowOpen
        humanReplyWindowUntil = conversation.humanReplyWindowUntil; replyBlockReason = conversation.replyBlockReason
        socialChannelId = conversation.socialChannelId; channelCapabilities = conversation.channelCapabilities
        lastInboundAt = conversation.lastInboundAt; resolvedAt = conversation.resolvedAt; firstReplyAt = conversation.firstReplyAt
        takenOverAt = conversation.takenOverAt; waitingSince = conversation.waitingSince; createdAt = conversation.createdAt
        updatedAt = conversation.updatedAt; messages = []
    }
}

struct InboxSummary: Codable, Equatable {
    var open: Int
    var resolved: Int
    var human: Int
    var ai: Int
    var unread: Int
    var mine: Int
    var unassigned: Int
}

struct PortalMember: Codable, Equatable, Identifiable {
    var id: String
    var name: String
    var email: String
    var availability: Availability
}

struct Team: Codable, Equatable, Identifiable {
    var id: String
    var name: String
    var description: String
    var strategy: String
    var channels: [String]
    var isDefault: Bool
    var members: [PortalMember]
    var openCount: Int
    var unassignedCount: Int
}

struct TeamUpdate: Codable {
    var name: String
    var description: String
    var strategy: String
    var channels: [String]
    var isDefault: Bool
    var memberIds: [String]
}

struct ReportDay: Codable, Equatable { var date: String; var started: Int; var resolved: Int }
struct ReportChannel: Codable, Equatable { var channel: String; var started: Int }
struct ReportAgent: Codable, Equatable { var name: String; var availability: String; var replies: Int; var assigned: Int; var openNow: Int }

struct PortalReport: Codable, Equatable {
    var started: Int
    var resolved: Int
    var openNow: Int
    var inboundMessages: Int
    var humanReplies: Int
    var aiReplies: Int
    var activeContacts: Int
    var agentsOnline: Int
    var avgFirstReplySeconds: Double?
    var avgResolutionSeconds: Double?
    var byDay: [ReportDay]
    var byChannel: [ReportChannel]
    var byAgent: [ReportAgent]
}

struct PortalChannel: Codable, Equatable, Identifiable {
    var channel: String
    var status: String
    var phoneNumber: String?
    var displayName: String?
    var supportsTemplates: Bool
    var id: String?
    var provider: String?
    var externalAccountId: String?
    var username: String?
    var capabilities: ChannelCapabilities?

    var listId: String { id ?? channel }
}

struct TemplateHeader: Codable, Equatable {
    var format: String
    var text: String = ""
    var parameters: [String] = []
}

struct TemplateButton: Codable, Equatable {
    var type: String
    var text: String = ""
    var url: String = ""
    var phoneNumber: String = ""
    var example: String = ""
    /// Takes a value at send time: a URL suffix or the code to copy.
    var dynamic: Bool = false
}

struct Template: Codable, Equatable, Identifiable {
    var id: String?
    var name: String
    var language: String
    var category: String
    var status: String
    var parameterFormat: String = "POSITIONAL"
    var header: TemplateHeader?
    var body: String
    var footer: String
    var buttons: [TemplateButton] = []
    /// Body variables in order, by name or number; `variables` is their count.
    var parameters: [String] = []
    var variables: Int
    var rejectedReason: String?

    var listId: String { "\(name):\(language)" }
}

struct TemplateLocation: Codable { var latitude: Double; var longitude: Double; var name: String; var address: String }

struct TemplateSend: Codable {
    var name: String
    var language: String
    /// Body values in the order of the template's parameters.
    var variables: [String]
    /// The header's variable, or the https link of its media.
    var headerValue: String = ""
    var location: TemplateLocation? = nil
    /// One slot per button; only the dynamic ones are read.
    var buttonValues: [String] = []
}

struct CannedReply: Codable, Equatable, Identifiable { var id: String; var shortcut: String; var content: String; var updatedAt: String }

struct Contact: Codable, Equatable, Identifiable {
    var id: String
    var name: String
    var phone: String?
    var email: String?
    var notes: String
    var tags: [ContactTag]?
    var createdAt: String
    var updatedAt: String
    var conversationCount: Int
    var openCount: Int
    var lastActivityAt: String?
}

struct ContactCreate: Codable { var name: String?; var phone: String; var email: String?; var notes: String? }

/// A PATCH body: an absent field keeps its value, `email: nil` is sent as null to clear it.
struct ContactUpdate: Encodable {
    var name: String?
    var phone: String?
    var email: String??
    var notes: String?

    func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: Keys.self)
        if let name { try container.encode(name, forKey: .name) }
        if let phone { try container.encode(phone, forKey: .phone) }
        if let email { try container.encode(email, forKey: .email) }
        if let notes { try container.encode(notes, forKey: .notes) }
    }

    enum Keys: String, CodingKey { case name, phone, email, notes }
}

enum ConversationStart: Encodable {
    case whatsapp(text: String)
    case whatsappCloud(template: TemplateSend)

    func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: Keys.self)
        switch self {
        case .whatsapp(let text):
            try container.encode("whatsapp", forKey: .channel)
            try container.encode(text, forKey: .text)
        case .whatsappCloud(let template):
            try container.encode("whatsapp_cloud", forKey: .channel)
            try container.encode(template, forKey: .template)
        }
    }

    enum Keys: String, CodingKey { case channel, text, template }
}

struct DeviceRegistration: Codable { var token: String; var provider: String; var platform: String }
struct DeviceOut: Codable { var registered: Bool; var provider: String }

/// Arbitrary JSON, for the variables an activity row carries.
enum JSONValue: Codable, Equatable {
    case string(String)
    case number(Double)
    case bool(Bool)
    case null
    case array([JSONValue])
    case object([String: JSONValue])

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if container.decodeNil() { self = .null }
        else if let value = try? container.decode(Bool.self) { self = .bool(value) }
        else if let value = try? container.decode(Double.self) { self = .number(value) }
        else if let value = try? container.decode(String.self) { self = .string(value) }
        else if let value = try? container.decode([JSONValue].self) { self = .array(value) }
        else if let value = try? container.decode([String: JSONValue].self) { self = .object(value) }
        else { throw DecodingError.dataCorruptedError(in: container, debugDescription: "Unsupported JSON value") }
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch self {
        case .string(let value): try container.encode(value)
        case .number(let value): try container.encode(value)
        case .bool(let value): try container.encode(value)
        case .null: try container.encodeNil()
        case .array(let value): try container.encode(value)
        case .object(let value): try container.encode(value)
        }
    }

    var stringValue: String? {
        if case .string(let value) = self { return value }
        return nil
    }

    /// How a variable reads inside an activity sentence.
    var displayString: String {
        switch self {
        case .string(let value): return value
        case .number(let value): return value == value.rounded() ? String(Int(value)) : String(value)
        case .bool(let value): return value ? "true" : "false"
        case .null: return ""
        case .array, .object: return ""
        }
    }
}

/// Timestamps arrive as ISO 8601 strings, with or without fractional seconds.
enum ISODate {
    private static let fractional: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return formatter
    }()
    private static let plain: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime]
        return formatter
    }()
    /// A naive timestamp with no zone designator, as some servers write.
    private static let naive: DateFormatter = {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(secondsFromGMT: 0)
        formatter.dateFormat = "yyyy-MM-dd'T'HH:mm:ss.SSSSSS"
        return formatter
    }()
    private static let naiveSeconds: DateFormatter = {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(secondsFromGMT: 0)
        formatter.dateFormat = "yyyy-MM-dd'T'HH:mm:ss"
        return formatter
    }()

    static func parse(_ value: String?) -> Date? {
        guard let value, !value.isEmpty else { return nil }
        if let date = fractional.date(from: value) ?? plain.date(from: value) { return date }
        let trimmed = value.split(separator: ".").first.map(String.init) ?? value
        return naive.date(from: value) ?? naiveSeconds.date(from: trimmed)
    }
}

struct ContactTag: Codable, Equatable, Identifiable {
    var id: String
    var name: String
    var color: String
    var contactCount: Int
    var routeTeamId: String?
    var routeTeamName: String?
    var routeAssigneeId: String?
    var routeAssigneeName: String?
}

struct ContactTagCreate: Codable { var name: String; var color: String? }
struct ContactTagUpdate: Codable { var name: String?; var color: String? }

struct CannedReplyCreate: Codable { var shortcut: String; var content: String }
struct CannedReplyUpdate: Codable { var shortcut: String?; var content: String? }

struct ContactTagsSet: Codable { var tagIds: [String] }

struct TemplateHeaderIn: Codable {
    var format: String
    var text: String = ""
    /// The sample handle from the upload endpoint, for media headers.
    var handle: String = ""
}

struct TemplateButtonIn: Codable {
    var type: String
    var text: String = ""
    var url: String = ""
    var phoneNumber: String = ""
    /// The URL suffix example or the copy code example.
    var example: String = ""
}

struct TemplateCreate: Codable {
    var name: String
    var language: String
    var category: String
    var header: TemplateHeaderIn?
    var body: String
    var footer: String
    var buttons: [TemplateButtonIn]
    /// One example per variable, by its name (or number).
    var examples: [String: String]
}

struct TemplateSampleOut: Codable { var handle: String }

/// One place a hosted sign-in opened: the server the app talks to from now on, and its session.
struct HostedAccount: Codable, Equatable, Identifiable {
    var server: String
    var session: Session
    var id: String { "\(server)|\(session.clientId)|\(session.userId ?? "")" }
}

struct HostedSignInResponse: Codable { var accounts: [HostedAccount] }
