import Foundation
import UserNotifications

/// Sound and a banner while the app is open, the way the web inbox does it.
///
/// The inbox polls; when a poll brings a conversation that now needs a person
/// (a new customer message in a human-handled case, or a case just assigned
/// to this person) a local notification is shown. It carries the conversation
/// id, so tapping it opens the thread through the same route a push does.
/// Nothing here needs a push service: it is the phone notifying itself.
@MainActor
final class LocalAlerts {
    static let shared = LocalAlerts()

    /// What the last poll looked like, so only changes make noise.
    private var seen: [String: Snapshot] = [:]
    private var primed = false
    private var asked = false

    private struct Snapshot: Equatable {
        let lastInboundAt: String
        let assigneeId: String?
        let unreadCount: Int
    }

    /// Ask once, the first time the inbox is shown, like the web does.
    func requestPermissionIfNeeded() {
        guard !asked else { return }
        asked = true
        Task {
            let center = UNUserNotificationCenter.current()
            let settings = await center.notificationSettings()
            guard settings.authorizationStatus == .notDetermined else { return }
            _ = try? await center.requestAuthorization(options: [.alert, .sound, .badge])
        }
    }

    /// Forget what was seen: a new session starts from its own first poll.
    func reset() {
        seen.removeAll()
        primed = false
    }

    /// Compare a fresh page of open conversations with the last one.
    func observe(_ rows: [Conversation], session: Session, openConversationId: String?) {
        var next: [String: Snapshot] = [:]
        var alerts: [Conversation] = []
        for row in rows where row.status == .open {
            let snapshot = Snapshot(lastInboundAt: row.lastInboundAt ?? "", assigneeId: row.assigneeId, unreadCount: row.unreadCount)
            next[row.id] = snapshot
            guard primed, row.mode == .human, row.id != openConversationId else { continue }
            let previous = seen[row.id]
            let newMessage = row.unreadCount > 0 && (previous == nil || previous!.lastInboundAt != snapshot.lastInboundAt)
            let assignedToMe = session.userId != nil && row.assigneeId == session.userId && previous?.assigneeId != row.assigneeId
            if newMessage || assignedToMe { alerts.append(row) }
        }
        // Rows that left the page keep their snapshot, so a case that scrolls
        // out and back in does not ring again for the same message.
        seen.merge(next) { _, fresh in fresh }
        primed = true
        for row in alerts { notify(row, session: session) }
    }

    private func notify(_ row: Conversation, session: Session) {
        let content = UNMutableNotificationContent()
        content.title = Conversations.name(row)
        content.subtitle = session.branding.clientName
        content.body = row.preview.isEmpty ? Strings.current.list.noMessages : row.preview
        content.sound = .default
        content.threadIdentifier = row.id
        content.userInfo = ["conversation_id": row.id, "client_id": session.clientId]
        let request = UNNotificationRequest(identifier: "inbox-\(row.id)-\(row.lastInboundAt ?? "")", content: content, trigger: nil)
        UNUserNotificationCenter.current().add(request)
    }
}
