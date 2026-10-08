import SwiftUI

@main
struct InboxApp: App {
    @UIApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate
    @State private var model = AppModel()
    @Environment(\.scenePhase) private var scenePhase

    var body: some Scene {
        WindowGroup {
            RootView()
                .environment(model)
                .task { await model.restore() }
                .onChange(of: scenePhase) { _, phase in model.scenePhaseChanged(phase) }
        }
    }
}

/// Picks the screen the model says is up and keeps the sign-out veil on top.
struct RootView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.colorScheme) private var scheme

    var body: some View {
        let palette = Palette.current(scheme)
        ZStack {
            palette.canvas.ignoresSafeArea()
            content(palette)
            if model.signOutBusy {
                palette.canvas.ignoresSafeArea()
                ProgressView().tint(palette.muted)
                    .accessibilityLabel(Strings.current.inbox.signOut)
            }
        }
        .alert(item: Binding(get: { model.alert }, set: { model.alert = $0 })) { alert in
            Alert(title: Text(alert.title), message: alert.message.map(Text.init), dismissButton: .default(Text(Strings.current.inbox.done)))
        }
    }

    @ViewBuilder
    private func content(_ palette: Palette) -> some View {
        if model.screen == .loading || model.privacyChecking {
            ProgressView().tint(palette.muted)
        } else if model.screen == .reconnect {
            ReconnectView()
        } else if model.screen == .signIn || model.session == nil {
            SignInView()
        } else if let session = model.session, !model.privacyApproved || model.screen == .privacy {
            PrivacyView(session: session, server: model.server, accepted: model.privacyApproved)
                .environment(\.accent, Accent(brandHex: session.branding.brandColor, scheme: scheme))
        } else if let session = model.session {
            MainTabsView()
                .environment(\.accent, Accent(brandHex: session.branding.brandColor, scheme: scheme))
        }
    }
}

struct ReconnectView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.colorScheme) private var scheme

    var body: some View {
        let palette = Palette.current(scheme)
        let s = Strings.current.inbox
        VStack(spacing: 12) {
            Text(s.reconnectTitle).font(.title2.weight(.bold)).foregroundStyle(palette.ink)
            Text(s.reconnectBody).font(.body).multilineTextAlignment(.center).foregroundStyle(palette.muted)
            Button { Task { await model.restore() } } label: {
                Text(s.retry).fontWeight(.bold).foregroundStyle(palette.ink).frame(minHeight: 48).padding(.horizontal, 24)
            }
            Button { Task { await model.signOut() } } label: {
                Text(s.signOut).foregroundStyle(palette.muted).frame(minHeight: 48).padding(.horizontal, 24)
            }
        }
        .padding(30)
    }
}

/// The workspace colour and palette for every signed-in screen.
private struct AccentKey: EnvironmentKey {
    static let defaultValue = Accent(brandHex: Theme.defaultBrand, scheme: .light)
}

extension EnvironmentValues {
    var accent: Accent {
        get { self[AccentKey.self] }
        set { self[AccentKey.self] = newValue }
    }
}
