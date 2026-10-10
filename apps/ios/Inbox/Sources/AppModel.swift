import Foundation
import Observation
import SwiftUI

/// The root state machine: which screen is up, which session it runs on, and
/// the privacy gate that sits between them.
@MainActor
@Observable
final class AppModel {
    enum Screen: Equatable { case loading, signIn, reconnect, privacy, main }
    enum Tab: Hashable { case inbox, contacts, reports, settings }

    struct AlertContent: Identifiable {
        let id = UUID()
        let title: String
        let message: String?
    }

    var screen: Screen = .loading
    var server = ""
    var session: Session?
    var privacyApproved = false
    var privacyChecking = false
    var signOutBusy = false
    var tab: Tab = .inbox
    var inboxPath: [Conversation] = []
    var contactsPath: [Conversation] = []
    var alert: AlertContent?

    private var authGeneration = 0
    private var pushSession: PushSession?
    private var pushKey: String?
    private var signingOut = false
    private var wasBackgrounded = false
    private var handledNotification = ""

    private let client = APIClient.shared

    init() {
        NotificationRouter.shared.handler = { [weak self] _ in self?.processPendingNotification() }
    }

    // MARK: Session lifecycle

    func restore() async {
        authGeneration += 1
        let generation = authGeneration
        privacyApproved = false
        screen = .loading
        guard let stored = SessionStore.load() else {
            screen = .signIn
            return
        }
        // The last launch's inbox is on screen while the server confirms the
        // session, as long as the disclosure it carries is the one accepted.
        var onSnapshot = false
        if let snapshot = SnapshotStore.load(server: stored.server, token: stored.token),
           ConsentStore.hasConsent(server: stored.server, session: snapshot.session) {
            client.setSessionAccess(snapshot.session, true)
            server = stored.server
            session = snapshot.session
            privacyApproved = true
            privacyChecking = false
            screen = .main
            onSnapshot = true
        }
        do {
            let next = try await PortalAPI.resumeSession(stored.server, token: stored.token)
            guard generation == authGeneration else { return }
            client.setSessionAccess(next, false)
            let approved = ConsentStore.hasConsent(server: stored.server, session: next)
            client.setSessionAccess(next, approved)
            server = stored.server
            session = next
            privacyApproved = approved
            privacyChecking = false
            screen = approved ? .main : .privacy
            syncPush()
            processPendingNotification()
        } catch let error as APIError where error.isUnauthorized {
            guard generation == authGeneration else { return }
            if let shown = session { client.setSessionAccess(shown, false) }
            try? SessionStore.clear()
            SnapshotStore.clear()
            session = nil
            server = ""
            privacyApproved = false
            screen = .signIn
        } catch {
            guard generation == authGeneration else { return }
            // An offline launch must not erase a valid login, nor hide an inbox already drawn.
            if !onSnapshot { screen = .reconnect }
        }
    }

    func signedIn(server base: String, session next: Session) throws {
        client.setSessionAccess(next, false)
        try SessionStore.store(StoredSession(server: base, token: next.token))
        let approved = ConsentStore.hasConsent(server: base, session: next)
        authGeneration += 1
        server = base
        session = next
        client.setSessionAccess(next, approved)
        privacyApproved = approved
        privacyChecking = false
        tab = .inbox
        inboxPath = []
        contactsPath = []
        screen = approved ? .main : .privacy
        syncPush()
    }

    func acceptPrivacy() throws {
        guard let session else { return }
        let generation = authGeneration
        try ConsentStore.accept(server: server, session: session)
        guard generation == authGeneration else { return }
        client.setSessionAccess(session, true)
        privacyApproved = true
        screen = .main
        syncPush()
        processPendingNotification()
    }

    func withdrawPrivacy() async throws {
        try ConsentStore.withdraw()
        if let session { client.setSessionAccess(session, false) }
        privacyApproved = false
        await signOut()
    }

    func showPrivacy() { screen = .privacy }
    func leavePrivacy() { if privacyApproved { screen = .main } }

    func signOut() async {
        guard !signingOut else { return }
        signingOut = true
        authGeneration += 1
        let previous = session
        if let previous { client.setSessionAccess(previous, false) }
        signOutBusy = true
        do {
            // A new account must not register the same native token before old
            // registration requests and their cleanup have finished.
            await stopPush()
            try SessionStore.clear()
            SnapshotStore.clear()
            ComposerDrafts.shared.clear()
            LocalAlerts.shared.reset()
            authGeneration += 1
            session = nil
            privacyApproved = false
            privacyChecking = false
            server = ""
            inboxPath = []
            contactsPath = []
            tab = .inbox
            screen = .signIn
            NotificationRouter.shared.clear()
        } catch {
            // Restore access if credential removal failed and the person remains signed in.
            if let previous {
                let approved = ConsentStore.hasConsent(server: server, session: previous)
                client.setSessionAccess(previous, approved)
                privacyApproved = approved
                syncPush()
            }
            alert = AlertContent(title: Strings.current.errors.generic, message: error.localizedDescription)
        }
        signingOut = false
        signOutBusy = false
    }

    func expireSession() {
        Task { await signOut() }
    }

    // MARK: Foreground and background

    func scenePhaseChanged(_ phase: ScenePhase) {
        guard let current = session else { return }
        // System permission dialogs are inactive, not background transitions.
        if phase == .inactive { return }
        if phase == .active && !wasBackgrounded { return }
        wasBackgrounded = phase != .active
        client.setSessionAccess(current, false)
        privacyChecking = true
        authGeneration += 1
        guard phase == .active else { return }
        // A consented session comes straight back on screen; the server's answer
        // only matters if it withdraws it or changes the disclosure.
        let keepShowing = privacyApproved && screen == .main
        if keepShowing {
            client.setSessionAccess(current, true)
            privacyChecking = false
        }
        let generation = authGeneration
        Task {
            do {
                let next = try await PortalAPI.resumeSession(server, token: current.token)
                guard generation == authGeneration, !signingOut else { return }
                let approved = ConsentStore.hasConsent(server: server, session: next)
                client.setSessionAccess(next, approved)
                if !approved { client.setSessionAccess(current, false) }
                session = next
                privacyApproved = approved
                privacyChecking = false
                if !approved { screen = .privacy }
                else if screen == .reconnect { screen = .main }
                syncPush()
                processPendingNotification()
            } catch let error as APIError where error.isUnauthorized {
                guard generation == authGeneration else { return }
                expireSession()
            } catch {
                guard generation == authGeneration else { return }
                privacyChecking = false
                if !keepShowing { screen = .reconnect }
            }
        }
    }

    // MARK: Navigation

    func openConversation(_ conversation: Conversation) {
        switch tab {
        case .contacts: contactsPath.append(conversation)
        case .inbox: inboxPath.append(conversation)
        case .reports, .settings:
            tab = .inbox
            inboxPath.append(conversation)
        }
    }

    // MARK: Notifications

    private func processPendingNotification() {
        guard let tap = NotificationRouter.shared.pending, let session, privacyApproved, !privacyChecking, !signOutBusy, screen == .main else { return }
        guard handledNotification != tap.identifier else { return }
        handledNotification = tap.identifier
        guard let id = NotificationTarget.conversationId(in: tap.userInfo, clientId: session.clientId) else {
            NotificationRouter.shared.clear()
            return
        }
        let generation = authGeneration
        Task {
            defer { NotificationRouter.shared.clear() }
            do {
                let detail = try await PortalAPI.conversation(server, session, id: id)
                guard generation == authGeneration else { return }
                tab = .inbox
                inboxPath = [detail.summary]
            } catch let error as APIError where error.isUnauthorized {
                expireSession()
            } catch {
                alert = AlertContent(title: Strings.current.inbox.notificationUnavailable, message: error.localizedDescription)
            }
        }
    }

    // MARK: Push

    private func syncPush() {
        guard let session, privacyApproved else {
            Task { await stopPush() }
            return
        }
        let key = "\(server)|\(session.token)|\(session.push.enabled)|\(session.push.provider)"
        guard key != pushKey else { return }
        let server = server
        Task {
            await stopPush()
            guard self.session?.token == session.token, privacyApproved else { return }
            pushKey = key
            let next = PushSession(server: server, session: session)
            pushSession = next
            next.start()
        }
    }

    private func stopPush() async {
        guard let current = pushSession else { return }
        pushSession = nil
        pushKey = nil
        await current.stop()
    }
}
