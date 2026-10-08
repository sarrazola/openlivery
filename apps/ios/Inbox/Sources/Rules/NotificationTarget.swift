import Foundation

/// A push selects a record, never a server or authentication identity.
enum NotificationTarget {
    static func conversationId(in userInfo: [AnyHashable: Any], clientId: String) -> String? {
        let data = NotificationData.normalize(userInfo)
        guard let id = data["conversation_id"] as? String else { return nil }
        let trimmed = id.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty, id.count <= 128 else { return nil }
        if let client = data["client_id"] {
            guard let client = client as? String, client == clientId else { return nil }
        }
        return id
    }
}
