import Foundation

extension Session {
    /// The server's current grants are authoritative, including an empty list.
    func has(_ permission: String) -> Bool {
        permissions?.contains(permission) ?? false
    }
}
