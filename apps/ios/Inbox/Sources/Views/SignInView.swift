import SwiftUI

/// Signing in.
///
/// A hosted build with a directory (see Brand.hostedSignInURL) asks for an
/// e-mail and a password and nothing else: the directory answers with the
/// account's own server, or with several accounts when the same person works
/// for more than one business. "Change server" leads to a screen for the
/// address of a core somebody runs themselves, and from there to a fresh login
/// against that server. A build with no hosted preset starts on the address.
struct SignInView: View {
    @Environment(\.colorScheme) private var scheme
    @State private var path: [Route] = []

    enum Route: Hashable {
        case server
        case login(String)
    }

    var body: some View {
        let accent = Accent(brandHex: Brand.primaryColorHex, scheme: scheme)
        NavigationStack(path: $path) {
            Group {
                if Brand.hosted != nil {
                    LoginForm(target: .hosted, path: $path)
                } else {
                    ServerEntry(path: $path, initial: Brand.defaultServer)
                }
            }
            .navigationDestination(for: Route.self) { route in
                switch route {
                case .server: ServerEntry(path: $path, initial: "")
                case .login(let server): LoginForm(target: .server(server), path: $path)
                }
            }
        }
        .tint(accent.color)
        .environment(\.accent, accent)
    }
}

/// The address of a server somebody runs themselves.
private struct ServerEntry: View {
    @Binding var path: [SignInView.Route]
    let initial: String
    @Environment(\.colorScheme) private var scheme
    @State private var draft: String
    @FocusState private var focused: Bool

    init(path: Binding<[SignInView.Route]>, initial: String) {
        _path = path
        self.initial = initial
        _draft = State(initialValue: initial)
    }

    var body: some View {
        let s = Strings.current.signIn
        let palette = Palette.current(scheme)
        ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                Image("BrandLogo")
                    .resizable().scaledToFit().frame(width: 56, height: 56)
                    .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
                    .accessibilityLabel(Brand.name)
                    .padding(.bottom, 28)
                Text(s.serverTitle).font(.system(size: 28, weight: .bold)).foregroundStyle(palette.ink)
                Text(s.serverHint).font(.subheadline).foregroundStyle(palette.muted).padding(.top, 8).padding(.bottom, 28)
                FieldLabel(text: s.serverLabel).padding(.bottom, 6)
                FormTextField(text: $draft, placeholder: s.serverPlaceholder, keyboard: .URL, contentType: .URL, autocapitalize: .never, accessibilityLabel: s.serverLabel) { proceed() }
                    .focused($focused)
                PrimaryButton(label: s.connect, disabled: APIClient.normalizeServerURL(draft).isEmpty, brandHex: Brand.primaryColorHex) { proceed() }
                    .padding(.top, 24)
                if let hosted = Brand.hosted {
                    Button(s.useHosted.replacingOccurrences(of: "{name}", with: hosted.label)) { path.removeAll() }
                        .foregroundStyle(palette.muted)
                        .frame(maxWidth: .infinity, minHeight: 44)
                        .padding(.top, 28)
                }
            }
            .padding(28)
            .padding(.top, 36)
            .frame(maxWidth: 560)
            .frame(maxWidth: .infinity)
        }
        .scrollDismissesKeyboard(.interactively)
        .background(palette.canvas)
        .toolbar(.hidden, for: .navigationBar)
        .onAppear { if draft.isEmpty { focused = true } }
    }

    private func proceed() {
        let normalized = APIClient.normalizeServerURL(draft)
        guard !normalized.isEmpty, let url = URL(string: normalized), url.host() != nil else { return }
        // Replace this step with the login, so Back from there returns to the start.
        if path.last == .server { path.removeLast() }
        path.append(.login(normalized))
    }
}

/// E-mail and password against one target: the hosted directory, or a server.
private struct LoginForm: View {
    enum Target: Equatable {
        case hosted
        case server(String)
    }

    let target: Target
    @Binding var path: [SignInView.Route]
    @Environment(AppModel.self) private var model
    @Environment(\.colorScheme) private var scheme
    @State private var email = ""
    @State private var password = ""
    @State private var busy = false
    @State private var error: String?
    @State private var forgot = false
    @State private var accounts: [HostedAccount] = []
    @State private var linkFailure: AppModel.AlertContent?
    @FocusState private var focus: Field?

    private enum Field { case email, password }

    private var canSubmit: Bool { !email.trimmingCharacters(in: .whitespaces).isEmpty && !password.isEmpty && !busy }

    private var connectedLabel: String {
        switch target {
        case .hosted: return Brand.hosted?.label ?? Brand.name
        case .server(let server): return URL(string: server)?.host() ?? server
        }
    }

    var body: some View {
        let palette = Palette.current(scheme)
        let s = Strings.current.signIn
        let p = PrivacyStrings.current
        let accent = Accent(brandHex: Brand.primaryColorHex, scheme: scheme)
        ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                Image("BrandLogo")
                    .resizable().scaledToFit().frame(width: 56, height: 56)
                    .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
                    .accessibilityLabel(Brand.name)
                    .padding(.bottom, 28)
                Text(s.title).font(.system(size: 28, weight: .bold)).foregroundStyle(palette.ink)
                Text(s.connectedTo.replacingOccurrences(of: "{name}", with: connectedLabel))
                    .font(.subheadline).foregroundStyle(palette.muted)
                    .padding(.top, 8)
                    .padding(.bottom, 28)

                FieldLabel(text: s.emailLabel).padding(.bottom, 6)
                FormTextField(text: $email, placeholder: s.emailPlaceholder, keyboard: .emailAddress, disabled: busy, contentType: .username, autocapitalize: .never, accessibilityLabel: s.emailLabel) { focus = .password }
                    .focused($focus, equals: .email)
                FieldLabel(text: s.passwordLabel).padding(.top, 16).padding(.bottom, 6)
                PasswordField(text: $password, disabled: busy, accessibilityLabel: s.passwordLabel) { Task { await submit() } }
                    .focused($focus, equals: .password)
                HStack {
                    Spacer()
                    Button(s.forgot) { forgot = true }.font(.subheadline).foregroundStyle(accent.color)
                }
                .padding(.top, 10)
                if let error {
                    Text(error).font(.subheadline).foregroundStyle(palette.danger).padding(.top, 12)
                }
                PrimaryButton(label: s.submit, busy: busy, disabled: !canSubmit, brandHex: Brand.primaryColorHex) { Task { await submit() } }
                    .padding(.top, 20)

                VStack(spacing: 4) {
                    switch target {
                    case .hosted:
                        Button(s.changeServer) { path.append(.server) }
                            .foregroundStyle(palette.muted)
                            .frame(minHeight: 44)
                    case .server:
                        if let hosted = Brand.hosted {
                            Button(s.useHosted.replacingOccurrences(of: "{name}", with: hosted.label)) { path.removeAll() }
                                .foregroundStyle(palette.muted)
                                .frame(minHeight: 44)
                        } else {
                            Button(s.changeServer) { path.removeAll() }
                                .foregroundStyle(palette.muted)
                                .frame(minHeight: 44)
                        }
                    }
                    HStack(spacing: 24) {
                        if let policy = Brand.privacyPolicyURL { Button(p.policy) { openExternal(policy, failure: $linkFailure) } }
                        if let support = Brand.supportURL { Button(p.support) { openExternal(support, failure: $linkFailure) } }
                    }
                    .font(.footnote)
                    .foregroundStyle(palette.muted)
                    .frame(minHeight: 36)
                }
                .frame(maxWidth: .infinity)
                .padding(.top, 28)
            }
            .padding(28)
            .padding(.top, 36)
            .frame(maxWidth: 560)
            .frame(maxWidth: .infinity)
        }
        .scrollDismissesKeyboard(.interactively)
        .background(palette.canvas)
        .toolbar(.hidden, for: .navigationBar)
        .alert(s.forgotTitle, isPresented: $forgot) {
            Button(Strings.current.inbox.done, role: .cancel) {}
        } message: { Text(s.forgotBody) }
        .alert(item: $linkFailure) { Alert(title: Text($0.title)) }
        .sheet(isPresented: Binding(get: { accounts.count > 1 }, set: { if !$0 { accounts = [] } })) { accountChooser }
    }

    /// The same e-mail opens more than one inbox: pick one.
    private var accountChooser: some View {
        let s = Strings.current.signIn
        let palette = Palette.current(scheme)
        return NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 8) {
                    Text(s.chooseAccountBody).font(.subheadline).foregroundStyle(palette.muted).padding(.bottom, 8)
                    ForEach(accounts) { account in
                        ActionRow(label: account.session.branding.clientName, subtitle: "\(account.session.branding.agencyName) · \(URL(string: account.server)?.host() ?? account.server)", symbol: "building.2") {
                            finish(account)
                        }
                    }
                }
                .padding(22)
            }
            .background(palette.surface)
            .navigationTitle(s.chooseAccount)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .topBarLeading) { Button(Strings.current.inbox.cancel) { accounts = [] } } }
        }
        .presentationDetents([.medium, .large])
    }

    private func finish(_ account: HostedAccount) {
        do {
            try model.signedIn(server: account.server, session: account.session)
            accounts = []
        } catch {
            self.error = Strings.current.signIn.failed
        }
    }

    private func submit() async {
        guard canSubmit else { return }
        let s = Strings.current.signIn
        busy = true
        error = nil
        defer { busy = false }
        let address = email.trimmingCharacters(in: .whitespaces)
        do {
            switch target {
            case .hosted:
                guard let directory = Brand.hostedSignInURL else {
                    // A hosted build with no directory has nowhere to send an e-mail alone.
                    path.append(.server)
                    return
                }
                do {
                    let found = try await PortalAPI.hostedSignIn(directory, email: address, password: password)
                    guard let first = found.first else { throw APIError(message: s.incorrectCredentials, status: 401) }
                    if found.count == 1 { finish(first) } else { accounts = found }
                } catch let failure as APIError where failure.status == 404 {
                    // The directory is not answering: a service problem, not a wrong address.
                    throw APIError(message: s.failed, status: 503)
                }
            case .server(let server):
                let session = try await PortalAPI.signIn(server, email: address, password: password)
                try model.signedIn(server: server, session: session)
            }
        } catch let failure as APIError {
            switch failure.status {
            case 404: error = s.workspaceUnavailable
            case 401: error = s.incorrectCredentials
            default: error = failure.message
            }
        } catch {
            self.error = s.failed
        }
    }
}
