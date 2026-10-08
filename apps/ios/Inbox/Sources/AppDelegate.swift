import UIKit
import UserNotifications

/// Receives the APNs token and notification taps, and hands both to the app.
final class AppDelegate: NSObject, UIApplicationDelegate, UNUserNotificationCenterDelegate {
    func application(_ application: UIApplication, didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil) -> Bool {
        UNUserNotificationCenter.current().delegate = self
        return true
    }

    func application(_ application: UIApplication, didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data) {
        Task { @MainActor in PushRegistrar.shared.didRegister(deviceToken) }
    }

    func application(_ application: UIApplication, didFailToRegisterForRemoteNotificationsWithError error: Error) {
        Task { @MainActor in PushRegistrar.shared.didFail() }
    }

    /// Show a banner even while the app is open; the inbox is not always on screen.
    func userNotificationCenter(_ center: UNUserNotificationCenter, willPresent notification: UNNotification) async -> UNNotificationPresentationOptions {
        [.banner, .list, .sound]
    }

    func userNotificationCenter(_ center: UNUserNotificationCenter, didReceive response: UNNotificationResponse) async {
        guard response.actionIdentifier == UNNotificationDefaultActionIdentifier else { return }
        let userInfo = response.notification.request.content.userInfo
        let identifier = response.notification.request.identifier
        await MainActor.run { NotificationRouter.shared.deliver(userInfo: userInfo, identifier: identifier) }
    }
}

/// Holds a tapped notification until the app is signed in and allowed to act on it.
@MainActor
final class NotificationRouter {
    static let shared = NotificationRouter()

    struct Tap { let userInfo: [AnyHashable: Any]; let identifier: String }

    private(set) var pending: Tap?
    var handler: ((Tap) -> Void)?

    func deliver(userInfo: [AnyHashable: Any], identifier: String) {
        let tap = Tap(userInfo: userInfo, identifier: identifier)
        pending = tap
        handler?(tap)
    }

    func clear() { pending = nil }
}
