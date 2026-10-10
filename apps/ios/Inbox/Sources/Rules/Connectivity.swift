import Foundation
import Network
import Observation

/// Whether the device currently has a route to the network.
///
/// Screens refresh the moment it comes back instead of waiting for their next
/// poll, which is what turns a stale cached inbox into a current one.
@MainActor
@Observable
final class Connectivity {
    static let shared = Connectivity()

    private(set) var online = true
    @ObservationIgnored private let monitor = NWPathMonitor()

    private init() {
        monitor.pathUpdateHandler = { [weak self] path in
            let satisfied = path.status == .satisfied
            Task { @MainActor in self?.online = satisfied }
        }
        monitor.start(queue: DispatchQueue(label: "inbox.connectivity"))
    }
}
