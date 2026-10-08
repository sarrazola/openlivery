import Foundation

/// Resolve only workspace names or addresses belonging to the configured service.
enum HostedServer {
    private static func validName(_ name: String) -> Bool {
        name.range(of: "^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$", options: .regularExpression) != nil
    }

    static func resolve(_ input: String, template: String) -> String? {
        let value = input.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        guard template.contains("{workspace}"), !value.isEmpty else { return nil }
        if validName(value) { return template.replacingOccurrences(of: "{workspace}", with: value) }
        guard let address = URL(string: value.contains("://") ? value : "https://\(value)"),
              let sample = URL(string: template.replacingOccurrences(of: "{workspace}", with: "workspace-placeholder")),
              let addressHost = address.host(), let sampleHost = sample.host() else { return nil }
        let parts = sampleHost.components(separatedBy: "workspace-placeholder")
        guard parts.count == 2 else { return nil }
        let prefix = parts[0], suffix = parts[1]
        guard address.scheme == "https", sample.scheme == "https",
              address.user == nil, address.password == nil, address.query == nil, address.fragment == nil,
              address.port == sample.port, normalizedPath(address) == normalizedPath(sample),
              addressHost.hasPrefix(prefix), addressHost.hasSuffix(suffix),
              addressHost.count >= prefix.count + suffix.count else { return nil }
        let start = addressHost.index(addressHost.startIndex, offsetBy: prefix.count)
        let end = addressHost.index(addressHost.endIndex, offsetBy: -suffix.count)
        let name = String(addressHost[start..<end])
        return validName(name) ? template.replacingOccurrences(of: "{workspace}", with: name) : nil
    }

    private static func normalizedPath(_ url: URL) -> String {
        let path = url.path()
        return path.isEmpty ? "/" : path
    }
}
