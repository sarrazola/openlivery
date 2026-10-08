import Foundation
import UIKit
import UserNotifications

/// Registering this install for notifications, without choosing a provider.
///
/// The app asks the operating system for the native APNs token and hands it to
/// the server, which delivers through whatever it was configured with. No push
/// vendor's SDK is involved, which is what lets the same build work against a
/// server that sends nothing, a server that POSTs to the operator's own webhook,
/// and a hosted one, without any of them borrowing another's account.
///
/// Two rules this module exists to keep:
///
/// 1. If the server says it cannot notify, ask for nothing. A permission prompt
///    that leads to no notifications trains people to say no, and a device that
///    subscribes to a push service nobody asked for costs whoever owns that
///    service money.
/// 2. Never let any of this break the app. Notifications are a convenience on
///    top of an inbox that already works by polling, so every failure here is
///    swallowed.
@MainActor
final class PushRegistrar {
    static let shared = PushRegistrar()

    private(set) var currentToken: String?
    private var waiters: [CheckedContinuation<String?, Never>] = []
    /// Called whenever APNs hands over a token while a session is active.
    var onToken: ((String) -> Void)?

    /// From the application delegate.
    func didRegister(_ deviceToken: Data) {
        let hex = deviceToken.map { String(format: "%02x", $0) }.joined()
        currentToken = hex
        let pending = waiters
        waiters.removeAll()
        pending.forEach { $0.resume(returning: hex) }
        onToken?(hex)
    }

    func didFail() {
        let pending = waiters
        waiters.removeAll()
        pending.forEach { $0.resume(returning: nil) }
    }

    private func awaitToken() async -> String? {
        if let currentToken { return currentToken }
        return await withCheckedContinuation { continuation in
            waiters.append(continuation)
            UIApplication.shared.registerForRemoteNotifications()
        }
    }

    func cancelWaiters() {
        let pending = waiters
        waiters.removeAll()
        pending.forEach { $0.resume(returning: nil) }
    }

    /// Ask for permission only if the server can send notifications, then get the token.
    func nativeToken() async -> String? {
        #if targetEnvironment(simulator)
        // A simulator has no push token to give, and asking would only produce a
        // permission prompt that can never lead to anything.
        return nil
        #else
        let center = UNUserNotificationCenter.current()
        let settings = await center.notificationSettings()
        var granted = [.authorized, .provisional, .ephemeral].contains(settings.authorizationStatus)
        if !granted, settings.authorizationStatus == .notDetermined {
            granted = (try? await center.requestAuthorization(options: [.alert, .sound, .badge])) ?? false
        }
        guard granted else { return nil }
        return await awaitToken()
        #endif
    }
}

/// One signed-in session's registration, disposed fully before another account
/// registers this install's native token.
@MainActor
final class PushSession {
    private let server: String
    private let session: Session
    private var registered: Set<String> = []
    private var task: Task<Void, Never>?
    private var active = true

    init(server: String, session: Session) {
        self.server = server
        self.session = session
    }

    func start() {
        guard session.push.enabled else { return }
        let registrar = PushRegistrar.shared
        registrar.onToken = { [weak self] token in
            guard let self, self.active else { return }
            Task { await self.register(token) }
        }
        task = Task { [weak self] in
            guard let self else { return }
            guard let token = await registrar.nativeToken(), self.active else { return }
            await self.register(token)
        }
    }

    private func register(_ token: String) async {
        do {
            _ = try await PortalAPI.registerDevice(server, session, DeviceRegistration(token: token, provider: session.push.provider, platform: "ios"))
            if active { registered.insert(token) }
        } catch {
            // A person can revoke permission at any time; not worth an error on screen.
        }
    }

    /// Release this install on sign-out so a shared phone stops ringing.
    func stop() async {
        active = false
        PushRegistrar.shared.onToken = nil
        PushRegistrar.shared.cancelWaiters()
        task?.cancel()
        _ = await task?.value
        for token in registered {
            // Signing out locally matters more than tidying the server's registry,
            // which drops the row anyway once the token stops accepting deliveries.
            try? await PortalAPI.forgetDevice(server, session, token: token)
        }
        registered.removeAll()
    }
}
