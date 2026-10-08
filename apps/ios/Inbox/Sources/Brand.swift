import Foundation
import SwiftUI

/// The identity this build was compiled with.
///
/// `Brand/Brand.xcconfig` is read by Xcode at build time and its values land in
/// Info.plist under the `Brand` key. Nothing here is fetched or configurable at
/// runtime: an app's identity is decided when it is built.
enum Brand {
    private static let values: [String: String] = {
        (Bundle.main.object(forInfoDictionaryKey: "Brand") as? [String: String]) ?? [:]
    }()

    private static func value(_ key: String) -> String {
        (values[key] ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
    }

    /// Addresses in the brand file carry no scheme (see Brand.xcconfig).
    private static func httpsURL(_ raw: String) -> URL? {
        let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return nil }
        let candidate = trimmed.contains("://") ? trimmed : "https://\(trimmed)"
        guard let url = URL(string: candidate), url.scheme == "https", url.host() != nil,
              url.user == nil, url.password == nil else { return nil }
        return url
    }

    static let name: String = {
        let display = Bundle.main.object(forInfoDictionaryKey: "CFBundleDisplayName") as? String
        let bundle = Bundle.main.object(forInfoDictionaryKey: "CFBundleName") as? String
        return [display, bundle].compactMap { $0 }.first { !$0.isEmpty } ?? "Inbox"
    }()

    /// Only the sign-in screen uses it; the workspace's own color arrives with the session.
    static let primaryColorHex: String = {
        let raw = value("PrimaryColor").replacingOccurrences(of: "#", with: "")
        return raw.count == 6 ? "#\(raw)" : Theme.defaultBrand
    }()

    static let defaultServer: String = {
        httpsURL(value("DefaultServer"))?.absoluteString ?? ""
    }()

    /// A preset for a service whoever published this build runs.
    ///
    /// There is none in this repository, on purpose: an open-source build should
    /// not point at somebody's hosted product. A build that has one offers it as
    /// a choice alongside typing an address; a build that does not just asks for
    /// the address, which is what a self-hosted install wants anyway.
    struct HostedPreset {
        let label: String
        /// `https://{workspace}.example.com`
        let serverTemplate: String
    }

    static let hosted: HostedPreset? = {
        let label = value("HostedLabel")
        let template = value("HostedServerTemplate")
        guard !label.isEmpty, template.contains("{workspace}") else { return nil }
        let withScheme = template.contains("://") ? template : "https://\(template)"
        guard withScheme.hasPrefix("https://") else { return nil }
        return HostedPreset(label: label, serverTemplate: withScheme)
    }()

    /// Where a hosted build signs in with an e-mail alone: a directory the
    /// publisher runs that answers with the account's own server. Without it, a
    /// hosted build asks for the workspace name and derives the address.
    static let hostedSignInURL: URL? = {
        guard hosted != nil else { return nil }
        let raw = value("HostedSignIn")
        guard !raw.isEmpty else { return nil }
        // Plain HTTP only for a development server on the local network.
        let normalized = APIClient.normalizeServerURL(raw)
        return normalized.hasPrefix("http://") ? URL(string: normalized) : httpsURL(raw)
    }()

    /// Turn what someone typed into the address their workspace lives at.
    static func hostedServer(for workspace: String) -> String {
        guard let hosted else { return "" }
        return HostedServer.resolve(workspace, template: hosted.serverTemplate) ?? ""
    }

    private static func localized(_ key: String) -> URL? {
        let language = AppLocale.languageCode
        let preferred = value("\(key)_\(language)")
        let fallback = value("\(key)_en")
        return httpsURL(preferred.isEmpty ? fallback : preferred)
    }

    static var privacyPolicyURL: URL? { localized("PrivacyPolicyURL") }
    static var supportURL: URL? { localized("SupportURL") }
}
