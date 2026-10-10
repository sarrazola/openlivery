import Foundation

/// What the last signed-in launch saw: the session's identity and the first
/// page of the open inbox, so the next launch draws them at once and refreshes
/// behind them instead of showing a spinner until the network answers.
///
/// The file never carries the credential; that stays in the Keychain and is
/// joined back in when the snapshot is read. It is protected until the device
/// is unlocked, excluded from backups, and removed on sign-out or when the
/// server no longer accepts the session.
struct Snapshot: Codable, Equatable {
    var server: String
    var session: Session
    var conversations: [Conversation]
    var summary: InboxSummary?
    var savedAt: Date
}

enum SnapshotStore {
    /// Enough rows to fill a screen a few times over; paging refills the rest.
    static let rowLimit = 40

    nonisolated(unsafe) static var directory: URL = {
        let base = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first ?? FileManager.default.temporaryDirectory
        return base.appending(path: "Inbox", directoryHint: .isDirectory)
    }()

    private static var file: URL { directory.appending(path: "snapshot.v1.json") }

    static func load(server: String, token: String) -> Snapshot? {
        guard let data = try? Data(contentsOf: file),
              var snapshot = try? APIClient.decoder.decode(Snapshot.self, from: data),
              snapshot.server == server, !token.isEmpty else { return nil }
        snapshot.session.token = token
        return snapshot
    }

    static func save(server: String, session: Session, conversations: [Conversation], summary: InboxSummary?) {
        var stripped = session
        stripped.token = ""
        let snapshot = Snapshot(server: server, session: stripped, conversations: Array(conversations.prefix(rowLimit)), summary: summary, savedAt: Date())
        guard let data = try? APIClient.encoder.encode(snapshot) else { return }
        let target = file
        do {
            try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
            try data.write(to: target, options: [.atomic, .completeFileProtection])
            var values = URLResourceValues()
            values.isExcludedFromBackup = true
            var url = target
            try? url.setResourceValues(values)
        } catch {
            // A launch without the snapshot is the state before this file existed.
        }
    }

    static func clear() {
        try? FileManager.default.removeItem(at: file)
    }
}
