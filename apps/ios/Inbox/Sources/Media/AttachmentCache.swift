import Foundation

/// Fetch an attachment into the cache once and hand back its local path.
///
/// The audio player asks for byte ranges as it goes, and those requests do not
/// carry the session, so streaming a credentialed URL stalls. Downloading first
/// sidesteps that and means replaying costs nothing.
enum AttachmentCache {
    private static var folder: URL {
        let base = FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask).first ?? FileManager.default.temporaryDirectory
        return base.appending(path: "attachments", directoryHint: .isDirectory)
    }

    /// FNV-1a over the URL: the server and portal are in it, so caches stay
    /// isolated even when two installations reuse an attachment identifier.
    private static func hash(_ text: String) -> String {
        var hash: UInt32 = 2166136261
        for byte in text.utf8 { hash = (hash ^ UInt32(byte)) &* 16777619 }
        return String(hash, radix: 16)
    }

    static func localURL(for remote: URL, id: String, extension ext: String) -> URL {
        folder.appending(path: "\(hash(remote.absoluteString))-\(id).\(ext)")
    }

    static func download(_ remote: URL, token: String, id: String, extension ext: String, force: Bool = false) async throws -> URL {
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        let target = localURL(for: remote, id: id, extension: ext)
        if force { try? FileManager.default.removeItem(at: target) }
        if let size = try? FileManager.default.attributesOfItem(atPath: target.path())[.size] as? Int, size > 0 { return target }
        do {
            let data = try await APIClient.shared.data(remote, token: token)
            try data.write(to: target, options: .atomic)
            return target
        } catch {
            // Never reuse a failed transfer.
            try? FileManager.default.removeItem(at: target)
            throw error
        }
    }

    /// Sent files and voice notes are staged here until the upload finishes.
    static func stagingURL(name: String) -> URL {
        let base = FileManager.default.temporaryDirectory.appending(path: "outgoing", directoryHint: .isDirectory)
        try? FileManager.default.createDirectory(at: base, withIntermediateDirectories: true)
        return base.appending(path: "\(UUID().uuidString)-\(name)")
    }
}

/// MIME types and extensions for what the pickers and the server hand over.
enum MimeTypes {
    static let images: [String: String] = ["jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp", "heic": "image/heic", "gif": "image/gif"]

    static func extensionFor(filename: String?, fallback: String) -> String {
        guard let filename, let match = filename.range(of: "\\.([a-zA-Z0-9]{1,8})$", options: .regularExpression) else { return fallback }
        return String(filename[match]).dropFirst().lowercased()
    }

    /// Native playback handles these; anything else is asked from the server as m4a.
    static let nativeAudio: Set<String> = ["audio/mp4", "audio/m4a", "audio/x-m4a", "audio/mpeg", "audio/mp3", "audio/wav", "audio/x-wav", "audio/aac"]

    static func audioExtension(_ mime: String) -> String {
        let base = mime.lowercased().split(separator: ";").first.map(String.init)?.trimmingCharacters(in: .whitespaces) ?? ""
        let table = ["audio/ogg": "ogg", "audio/opus": "ogg", "video/ogg": "ogg", "audio/webm": "webm", "audio/mpeg": "mp3", "audio/mp3": "mp3", "audio/wav": "wav", "audio/x-wav": "wav", "audio/aac": "aac", "audio/flac": "flac"]
        return table[base] ?? "m4a"
    }

    static func humanSize(_ bytes: Int) -> String {
        guard bytes > 0 else { return "" }
        if bytes < 1024 { return "\(bytes) B" }
        if bytes < 1024 * 1024 { return "\(Int((Double(bytes) / 1024).rounded())) KB" }
        return String(format: "%.1f MB", Double(bytes) / (1024 * 1024))
    }
}
