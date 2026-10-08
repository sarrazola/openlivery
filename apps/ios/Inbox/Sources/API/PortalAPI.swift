import Foundation

/// The portal endpoints the app calls, one function per route.
enum PortalAPI {
    private static var client: APIClient { APIClient.shared }
    private static func enc(_ value: String) -> String { APIClient.encodePathComponent(value) }
    private static func portal(_ session: Session, _ path: String) -> String { APIClient.portalPath(session, path) }

    struct ConversationFilters {
        var status: ConversationStatus?
        var mode: ConversationMode?
        var assignee: String?
        var team: String?
        var unread = false
        var channel: String?
        var search: String?
        var limit: Int?
        var offset: Int?
    }

    /// Only advertised filters are sent; the server owns unread and assignment semantics.
    static func conversationQuery(_ options: ConversationFilters) -> String {
        var items: [URLQueryItem] = []
        if let status = options.status { items.append(URLQueryItem(name: "status", value: status.rawValue)) }
        if let mode = options.mode { items.append(URLQueryItem(name: "mode", value: mode.rawValue)) }
        if let assignee = options.assignee, !assignee.isEmpty { items.append(URLQueryItem(name: "assignee", value: assignee)) }
        if let team = options.team, !team.isEmpty { items.append(URLQueryItem(name: "team", value: team)) }
        if let channel = options.channel, !channel.isEmpty { items.append(URLQueryItem(name: "channel", value: channel)) }
        if let search = options.search?.trimmingCharacters(in: .whitespacesAndNewlines), !search.isEmpty { items.append(URLQueryItem(name: "search", value: search)) }
        if options.unread { items.append(URLQueryItem(name: "unread", value: "true")) }
        if let limit = options.limit { items.append(URLQueryItem(name: "limit", value: String(min(200, max(1, limit))))) }
        if let offset = options.offset { items.append(URLQueryItem(name: "offset", value: String(max(0, offset)))) }
        guard !items.isEmpty else { return "" }
        var components = URLComponents()
        components.queryItems = items
        return components.percentEncodedQuery.map { "?\($0)" } ?? ""
    }

    static func signIn(_ server: String, email: String, password: String) async throws -> Session {
        struct Body: Encodable { let email: String; let password: String }
        return try await client.request(server, "/mobile/sign-in", method: "POST", body: Body(email: email, password: password))
    }

    /// Sign in by e-mail alone through the hosted service's directory, which
    /// answers with every account the credentials open and the server of each.
    static func hostedSignIn(_ url: URL, email: String, password: String) async throws -> [HostedAccount] {
        struct Body: Encodable { let email: String; let password: String }
        let response: HostedSignInResponse = try await client.request(url: url, method: "POST", body: Body(email: email, password: password))
        return response.accounts
    }

    /// Re-checks a stored token on launch and refreshes branding the agency may have changed.
    static func resumeSession(_ server: String, token: String) async throws -> Session {
        try await client.request(server, "/mobile/session", token: token)
    }

    static func listConversations(_ server: String, _ session: Session, _ options: ConversationFilters) async throws -> [Conversation] {
        try await client.request(server, portal(session, "/conversations\(conversationQuery(options))"), token: session.token)
    }

    static func inboxSummary(_ server: String, _ session: Session) async throws -> InboxSummary {
        try await client.request(server, portal(session, "/conversations/summary"), token: session.token)
    }

    static func conversation(_ server: String, _ session: Session, id: String) async throws -> ConversationDetail {
        try await client.request(server, portal(session, "/conversations/\(enc(id))"), token: session.token)
    }

    private static func change(_ server: String, _ session: Session, id: String, action: String, method: String, body: any Encodable) async throws -> ConversationDetail {
        try await client.request(server, portal(session, "/conversations/\(enc(id))/\(action)"), method: method, body: body, token: session.token)
    }

    static func setMode(_ server: String, _ session: Session, id: String, mode: ConversationMode) async throws -> ConversationDetail {
        struct Body: Encodable { let mode: ConversationMode }
        return try await change(server, session, id: id, action: "mode", method: "PATCH", body: Body(mode: mode))
    }

    /// Resolved cases are final. New customer messages create another case.
    static func resolve(_ server: String, _ session: Session, id: String) async throws -> ConversationDetail {
        struct Body: Encodable { let status: String }
        return try await change(server, session, id: id, action: "status", method: "PATCH", body: Body(status: "resolved"))
    }

    static func assign(_ server: String, _ session: Session, id: String, assigneeId: String) async throws -> ConversationDetail {
        struct Body: Encodable { let assigneeId: String }
        return try await change(server, session, id: id, action: "assignment", method: "POST", body: Body(assigneeId: assigneeId))
    }

    static func setTeam(_ server: String, _ session: Session, id: String, teamId: String?) async throws -> ConversationDetail {
        struct Body: Encodable {
            let teamId: String?
            func encode(to encoder: Encoder) throws {
                var container = encoder.container(keyedBy: Keys.self)
                try container.encode(teamId, forKey: .teamId)
            }
            enum Keys: String, CodingKey { case teamId = "team_id" }
        }
        return try await change(server, session, id: id, action: "team", method: "PATCH", body: Body(teamId: teamId))
    }

    static func markRead(_ server: String, _ session: Session, id: String) async throws {
        try await client.requestVoid(server, portal(session, "/conversations/\(enc(id))/read"), method: "POST", token: session.token)
    }

    static func reply(_ server: String, _ session: Session, id: String, content: String, quotedMessageId: String?) async throws -> ConversationDetail {
        struct Body: Encodable {
            let content: String
            let quotedMessageId: String?
            func encode(to encoder: Encoder) throws {
                var container = encoder.container(keyedBy: Keys.self)
                try container.encode(content, forKey: .content)
                try container.encode(quotedMessageId, forKey: .quotedMessageId)
            }
            enum Keys: String, CodingKey { case content, quotedMessageId = "quoted_message_id" }
        }
        return try await change(server, session, id: id, action: "reply", method: "POST", body: Body(content: content, quotedMessageId: quotedMessageId))
    }

    static func react(_ server: String, _ session: Session, id: String, messageId: String, emoji: String) async throws -> ConversationDetail {
        struct Body: Encodable { let emoji: String }
        return try await change(server, session, id: id, action: "messages/\(enc(messageId))/reaction", method: "POST", body: Body(emoji: emoji))
    }

    static func replyWithTemplate(_ server: String, _ session: Session, id: String, template: TemplateSend) async throws -> ConversationDetail {
        try await change(server, session, id: id, action: "reply-template", method: "POST", body: template)
    }

    static func replyWithFile(_ server: String, _ session: Session, id: String, file: OutgoingFile, caption: String) async throws -> ConversationDetail {
        try await client.upload(server, portal(session, "/conversations/\(enc(id))/reply-media"), token: session.token, file: file, caption: caption)
    }

    /// Where an attachment can be fetched from, with the session's credentials.
    static func attachmentURL(_ server: String, _ session: Session, conversationId: String, attachmentId: String) -> URL? {
        URL(string: "\(server)/api\(portal(session, "/conversations/\(enc(conversationId))/attachments/\(enc(attachmentId))"))")
    }

    static func members(_ server: String, _ session: Session) async throws -> [PortalMember] {
        try await client.request(server, portal(session, "/members"), token: session.token)
    }

    static func teams(_ server: String, _ session: Session) async throws -> [Team] {
        try await client.request(server, portal(session, "/teams"), token: session.token)
    }

    static func createTeam(_ server: String, _ session: Session, _ team: TeamUpdate) async throws -> Team {
        try await client.request(server, portal(session, "/teams"), method: "POST", body: team, token: session.token)
    }

    static func updateTeam(_ server: String, _ session: Session, id: String, _ team: TeamUpdate) async throws -> Team {
        try await client.request(server, portal(session, "/teams/\(enc(id))"), method: "PATCH", body: team, token: session.token)
    }

    struct ReportFilters {
        var from: String
        var to: String
        var tzOffset: Int
        var channel: String?
        var teamId: String?
    }

    static func report(_ server: String, _ session: Session, _ filters: ReportFilters) async throws -> PortalReport {
        var items = [URLQueryItem(name: "from", value: filters.from), URLQueryItem(name: "to", value: filters.to), URLQueryItem(name: "tz_offset", value: String(filters.tzOffset))]
        if let channel = filters.channel, !channel.isEmpty { items.append(URLQueryItem(name: "channel", value: channel)) }
        if let team = filters.teamId, !team.isEmpty { items.append(URLQueryItem(name: "team_id", value: team)) }
        var components = URLComponents()
        components.queryItems = items
        return try await client.request(server, portal(session, "/reports?\(components.percentEncodedQuery ?? "")"), token: session.token)
    }

    static func setAvailability(_ server: String, _ session: Session, _ availability: Availability) async throws -> PortalMember {
        struct Body: Encodable { let availability: Availability }
        return try await client.request(server, portal(session, "/me"), method: "PATCH", body: Body(availability: availability), token: session.token)
    }

    static func channels(_ server: String, _ session: Session) async throws -> [PortalChannel] {
        try await client.request(server, portal(session, "/channels"), token: session.token)
    }

    static func templates(_ server: String, _ session: Session) async throws -> [Template] {
        try await client.request(server, portal(session, "/templates"), token: session.token)
    }

    static func cannedReplies(_ server: String, _ session: Session) async throws -> [CannedReply] {
        try await client.request(server, portal(session, "/canned-responses"), token: session.token)
    }

    static func contacts(_ server: String, _ session: Session, search: String?, limit: Int, offset: Int) async throws -> [Contact] {
        let query = conversationQuery(ConversationFilters(search: search, limit: limit, offset: offset))
        return try await client.request(server, portal(session, "/contacts\(query)"), token: session.token)
    }

    static func contact(_ server: String, _ session: Session, id: String) async throws -> Contact {
        try await client.request(server, portal(session, "/contacts/\(enc(id))"), token: session.token)
    }

    static func createContact(_ server: String, _ session: Session, _ contact: ContactCreate) async throws -> Contact {
        try await client.request(server, portal(session, "/contacts"), method: "POST", body: contact, token: session.token)
    }

    static func updateContact(_ server: String, _ session: Session, id: String, _ contact: ContactUpdate) async throws -> Contact {
        try await client.request(server, portal(session, "/contacts/\(enc(id))"), method: "PATCH", body: contact, token: session.token)
    }

    static func contactConversations(_ server: String, _ session: Session, id: String) async throws -> [Conversation] {
        try await client.request(server, portal(session, "/contacts/\(enc(id))/conversations"), token: session.token)
    }

    static func startConversation(_ server: String, _ session: Session, contactId: String, _ payload: ConversationStart) async throws -> ConversationDetail {
        try await client.request(server, portal(session, "/contacts/\(enc(contactId))/conversations"), method: "POST", body: payload, token: session.token)
    }

    /// Tell the server where to reach this install.
    static func registerDevice(_ server: String, _ session: Session, _ device: DeviceRegistration) async throws -> DeviceOut {
        try await client.request(server, "/mobile/devices", method: "POST", body: device, token: session.token)
    }

    /// Stop notifying this install, on sign-out.
    static func forgetDevice(_ server: String, _ session: Session, token: String) async throws {
        try await client.requestVoid(server, "/mobile/devices/\(enc(token))", method: "DELETE", token: session.token)
    }

    static func assetURL(_ server: String, _ path: String?) -> URL? {
        guard let path, !path.isEmpty else { return nil }
        return URL(string: path.hasPrefix("http") ? path : "\(server)\(path)")
    }
}

extension PortalAPI {
    static func tags(_ server: String, _ session: Session) async throws -> [ContactTag] {
        try await APIClient.shared.request(server, APIClient.portalPath(session, "/tags"), token: session.token)
    }

    static func createTag(_ server: String, _ session: Session, _ tag: ContactTagCreate) async throws -> ContactTag {
        try await APIClient.shared.request(server, APIClient.portalPath(session, "/tags"), method: "POST", body: tag, token: session.token)
    }

    static func updateTag(_ server: String, _ session: Session, id: String, _ tag: ContactTagUpdate) async throws -> ContactTag {
        try await APIClient.shared.request(server, APIClient.portalPath(session, "/tags/\(APIClient.encodePathComponent(id))"), method: "PATCH", body: tag, token: session.token)
    }

    static func deleteTag(_ server: String, _ session: Session, id: String) async throws {
        try await APIClient.shared.requestVoid(server, APIClient.portalPath(session, "/tags/\(APIClient.encodePathComponent(id))"), method: "DELETE", token: session.token)
    }

    static func createCannedReply(_ server: String, _ session: Session, _ reply: CannedReplyCreate) async throws -> CannedReply {
        try await APIClient.shared.request(server, APIClient.portalPath(session, "/canned-responses"), method: "POST", body: reply, token: session.token)
    }

    static func updateCannedReply(_ server: String, _ session: Session, id: String, _ reply: CannedReplyUpdate) async throws -> CannedReply {
        try await APIClient.shared.request(server, APIClient.portalPath(session, "/canned-responses/\(APIClient.encodePathComponent(id))"), method: "PATCH", body: reply, token: session.token)
    }

    static func deleteCannedReply(_ server: String, _ session: Session, id: String) async throws {
        try await APIClient.shared.requestVoid(server, APIClient.portalPath(session, "/canned-responses/\(APIClient.encodePathComponent(id))"), method: "DELETE", token: session.token)
    }

    static func createTemplate(_ server: String, _ session: Session, _ template: TemplateCreate) async throws -> Template {
        try await APIClient.shared.request(server, APIClient.portalPath(session, "/templates"), method: "POST", body: template, token: session.token)
    }

    static func deleteTemplate(_ server: String, _ session: Session, name: String) async throws {
        try await APIClient.shared.requestVoid(server, APIClient.portalPath(session, "/templates/\(APIClient.encodePathComponent(name))"), method: "DELETE", token: session.token)
    }
}

extension PortalAPI {
    /// Replace the contact's tags with the given set.
    static func setContactTags(_ server: String, _ session: Session, id: String, tagIds: [String]) async throws -> Contact {
        try await APIClient.shared.request(server, APIClient.portalPath(session, "/contacts/\(APIClient.encodePathComponent(id))/tags"), method: "PUT", body: ContactTagsSet(tagIds: tagIds), token: session.token)
    }

    /// Store the sample file a media header is reviewed with; the handle goes into the template.
    static func uploadTemplateSample(_ server: String, _ session: Session, file: OutgoingFile) async throws -> TemplateSampleOut {
        try await APIClient.shared.upload(server, APIClient.portalPath(session, "/templates/samples"), token: session.token, file: file, caption: "")
    }
}
