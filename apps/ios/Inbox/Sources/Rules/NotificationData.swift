import Foundation

/// Delivery adapters may normalize their native envelope at this boundary.
///
/// A publisher whose notification service wraps the payload replaces this one
/// file in their build; the rest of the app only ever sees a flat dictionary.
enum NotificationData {
    static func normalize(_ userInfo: [AnyHashable: Any]) -> [String: Any] {
        var result: [String: Any] = [:]
        for (key, value) in userInfo {
            if let key = key as? String { result[key] = value }
        }
        return result
    }
}
