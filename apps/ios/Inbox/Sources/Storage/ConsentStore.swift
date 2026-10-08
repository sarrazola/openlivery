import Foundation

/// Permission is specific to the account, workspace and disclosed processing.
///
/// What is stored is a fingerprint of the disclosure the person accepted. A new
/// destination, a new disclosure version, another workspace or another account
/// all produce a different fingerprint, so the screen is shown again.
enum ConsentStore {
    private static let key = "inbox.privacy.v1"

    static func fingerprint(server: String, session: Session) -> String? {
        guard let privacy = session.privacy, !privacy.version.isEmpty else { return nil }
        let kinds: Set<String> = ["ai", "integration", "notification"]
        guard privacy.destinations.allSatisfy({ kinds.contains($0.kind) }) else { return nil }
        guard let url = URL(string: server), let scheme = url.scheme, ["http", "https"].contains(scheme),
              url.user == nil, url.password == nil, let host = url.host() else { return nil }
        var path = url.path()
        while path.hasSuffix("/") { path.removeLast() }
        let port = url.port.map { ":\($0)" } ?? ""
        let origin = "\(scheme)://\(host)\(port)\(path)"
        let destinations = privacy.destinations
            .map { destination -> String in
                let capabilities = destination.capabilities.sorted().joined(separator: ",")
                return "\(destination.kind)|\(destination.name)|\(destination.host)|\(capabilities)"
            }
            .sorted()
            .joined(separator: ";")
        return [
            "policy=1", "server=\(origin)", "client=\(session.clientId)", "user=\(session.userId ?? "legacy")",
            "version=\(privacy.version)", "destinations=\(destinations)",
        ].joined(separator: "\n")
    }

    static func hasConsent(server: String, session: Session) -> Bool {
        guard let expected = fingerprint(server: server, session: session) else { return false }
        return (try? Keychain.read(key)) == expected
    }

    struct MissingDisclosure: Error {}

    static func accept(server: String, session: Session) throws {
        guard let value = fingerprint(server: server, session: session) else { throw MissingDisclosure() }
        try Keychain.write(key, value)
    }

    static func withdraw() throws {
        try Keychain.delete(key)
    }
}
