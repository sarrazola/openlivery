import Foundation

/// The threads opened most recently, kept on disk so they open at once and
/// still read without a connection.
///
/// Bounded on purpose: a fixed number of threads, each cut to its latest
/// messages, text only (attachments stay in their own cache and download when
/// tapped). The least recently opened thread goes first when the limit is
/// reached. Sign-out and a rejected session remove the directory.
enum ThreadCache {
    static let threadLimit = 30
    static let messageLimit = 60
    /// How many of the newest open conversations the inbox fetches ahead.
    static let prefetchLimit = 10

    nonisolated(unsafe) static var directory: URL = SnapshotStore.directory.appending(path: "threads", directoryHint: .isDirectory)
    /// The `updatedAt` of every cached thread, so the inbox can tell which ones moved.
    nonisolated(unsafe) private static var stamps: [String: String] = [:]
    nonisolated(unsafe) private static var stampsLoaded = false
    private static let lock = NSLock()

    private static func file(_ id: String) -> URL {
        directory.appending(path: "\(id.filter { $0.isLetter || $0.isNumber || $0 == "-" }).json")
    }

    static func load(_ id: String) -> ConversationDetail? {
        guard let data = try? Data(contentsOf: file(id)),
              let detail = try? APIClient.decoder.decode(ConversationDetail.self, from: data), detail.id == id else { return nil }
        // Opening a thread makes it the most recent one.
        try? FileManager.default.setAttributes([.modificationDate: Date()], ofItemAtPath: file(id).path())
        return detail
    }

    static func updatedAt(_ id: String) -> String? {
        lock.lock(); defer { lock.unlock() }
        if !stampsLoaded {
            stampsLoaded = true
            for url in files() {
                if let data = try? Data(contentsOf: url), let detail = try? APIClient.decoder.decode(ConversationDetail.self, from: data) {
                    stamps[detail.id] = detail.updatedAt
                }
            }
        }
        return stamps[id]
    }

    static func save(_ detail: ConversationDetail) {
        var trimmed = detail
        trimmed.messages = Array(detail.messages.suffix(messageLimit))
        guard let data = try? APIClient.encoder.encode(trimmed) else { return }
        do {
            try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
            try data.write(to: file(detail.id), options: [.atomic, .completeFileProtection])
            var values = URLResourceValues()
            values.isExcludedFromBackup = true
            var url = file(detail.id)
            try? url.setResourceValues(values)
        } catch {
            return
        }
        lock.lock(); stamps[detail.id] = detail.updatedAt; lock.unlock()
        prune()
    }

    static func clear() {
        try? FileManager.default.removeItem(at: directory)
        lock.lock(); stamps = [:]; stampsLoaded = true; lock.unlock()
    }

    private static func files() -> [URL] {
        (try? FileManager.default.contentsOfDirectory(at: directory, includingPropertiesForKeys: [.contentModificationDateKey])) ?? []
    }

    private static func prune() {
        let dated = files().map { url -> (URL, Date) in
            (url, (try? url.resourceValues(forKeys: [.contentModificationDateKey]).contentModificationDate) ?? .distantPast)
        }
        guard dated.count > threadLimit else { return }
        for (url, _) in dated.sorted { $0.1 > $1.1 }.dropFirst(threadLimit) {
            try? FileManager.default.removeItem(at: url)
            let id = url.deletingPathExtension().lastPathComponent
            lock.lock(); stamps[id] = nil; lock.unlock()
        }
    }
}
