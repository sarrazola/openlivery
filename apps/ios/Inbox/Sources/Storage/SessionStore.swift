import Foundation

/// Store bearer credentials in the operating system's encrypted credential store.
struct StoredSession: Codable, Equatable {
    var server: String
    var token: String
}

enum SessionStore {
    private static let key = "inbox.session.v2"

    private static func parse(_ raw: String?) -> StoredSession? {
        guard let raw, let data = raw.data(using: .utf8),
              let session = try? JSONDecoder().decode(StoredSession.self, from: data),
              !session.token.isEmpty, let url = URL(string: session.server),
              let scheme = url.scheme, ["http", "https"].contains(scheme), url.user == nil, url.password == nil else { return nil }
        return session
    }

    static func load() -> StoredSession? {
        parse(try? Keychain.read(key))
    }

    /// Never fall back to plaintext if the device cannot persist a credential.
    static func store(_ session: StoredSession) throws {
        let data = try JSONEncoder().encode(session)
        try Keychain.write(key, String(decoding: data, as: UTF8.self))
    }

    static func clear() throws {
        try Keychain.delete(key)
    }
}
