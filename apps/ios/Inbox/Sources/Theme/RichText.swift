import Foundation
import SwiftUI

/// Renders the light markdown that reaches chat bubbles.
///
/// Models reply with **bold** and *italics* whether or not anyone asked, and the
/// web portal already renders it, so leaving the asterisks visible here would be
/// the app showing raw text the rest of the product formats. Only bold, italics
/// and inline code are handled: a chat bubble has no use for headings or tables.
enum RichText {
    private static let pattern = try! NSRegularExpression(pattern: "(\\*\\*[^*]+\\*\\*|\\*[^*\\n]+\\*|_[^_\\n]+_|`[^`\\n]+`)")

    static func attributed(_ text: String) -> AttributedString {
        guard !text.isEmpty else { return AttributedString() }
        var result = AttributedString()
        let nsText = text as NSString
        var cursor = 0
        for match in pattern.matches(in: text, range: NSRange(location: 0, length: nsText.length)) {
            let range = match.range
            if range.location > cursor {
                result.append(AttributedString(nsText.substring(with: NSRange(location: cursor, length: range.location - cursor))))
            }
            let token = nsText.substring(with: range)
            result.append(styled(token))
            cursor = range.location + range.length
        }
        if cursor < nsText.length { result.append(AttributedString(nsText.substring(from: cursor))) }
        return result
    }

    private static func styled(_ token: String) -> AttributedString {
        if token.hasPrefix("**"), token.hasSuffix("**"), token.count > 4 {
            var part = AttributedString(String(token.dropFirst(2).dropLast(2)))
            part.font = .body.weight(.bold)
            return part
        }
        if (token.hasPrefix("*") && token.hasSuffix("*")) || (token.hasPrefix("_") && token.hasSuffix("_")), token.count > 2 {
            var part = AttributedString(String(token.dropFirst().dropLast()))
            part.font = .body.italic()
            return part
        }
        if token.hasPrefix("`"), token.hasSuffix("`"), token.count > 2 {
            var part = AttributedString(String(token.dropFirst().dropLast()))
            part.font = .system(.body, design: .monospaced)
            return part
        }
        return AttributedString(token)
    }
}
