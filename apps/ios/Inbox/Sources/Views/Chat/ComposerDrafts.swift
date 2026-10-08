import Foundation

/// Unsent text and files, kept per conversation for the life of the session.
///
/// Drafts never persist to disk: signing out clears them, and a draft written
/// under one account is never shown to the next.
@MainActor
final class ComposerDrafts {
    static let shared = ComposerDrafts()

    struct Draft { var text: String; var file: OutgoingFile? }

    private var drafts: [String: Draft] = [:]
    private var order: [String] = []
    private(set) var epoch = 0

    func get(_ key: String) -> Draft? { drafts[key] }

    func set(_ key: String, _ draft: Draft) {
        if draft.text.isEmpty && draft.file == nil {
            remove(key)
            return
        }
        if drafts[key] == nil { order.append(key) }
        drafts[key] = draft
        while order.count > 50, let oldest = order.first {
            order.removeFirst()
            drafts.removeValue(forKey: oldest)
        }
    }

    func remove(_ key: String) {
        drafts.removeValue(forKey: key)
        order.removeAll { $0 == key }
    }

    func clear() {
        drafts.removeAll()
        order.removeAll()
        epoch += 1
    }
}
