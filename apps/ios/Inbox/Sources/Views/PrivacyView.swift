import SwiftUI

/// What the workspace does with a person's information, and their consent to it.
///
/// Accepting is possible only once the whole disclosure has scrolled past, the
/// way a terms screen works, so nobody consents to a page they have not seen.
struct PrivacyView: View {
    let session: Session
    let server: String
    let accepted: Bool
    @Environment(AppModel.self) private var model
    @Environment(\.accent) private var accent
    @State private var busy: String?
    @State private var error: String?
    @State private var confirmWithdraw = false
    @State private var linkFailure: AppModel.AlertContent?
    @State private var reachedEnd = false

    var body: some View {
        let p = PrivacyStrings.current
        let palette = accent.palette
        let disclosure = session.privacy
        let serverHost = URL(string: server)?.host() ?? server
        let unavailable = disclosure?.version.isEmpty ?? true
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    Text(accepted ? p.reviewIntro : p.intro).font(.title3.weight(.bold)).foregroundStyle(palette.ink).padding(.bottom, 4)
                    HStack(spacing: 12) {
                        Avatar(name: session.branding.clientName, size: 44, radius: 14, fontSize: 18)
                        VStack(alignment: .leading, spacing: 2) {
                            Text(p.account).font(.caption).foregroundStyle(palette.muted)
                            Text(session.branding.clientName).font(.subheadline.weight(.semibold)).foregroundStyle(palette.ink)
                            Text(serverHost).font(.caption).foregroundStyle(palette.muted).textSelection(.enabled)
                        }
                        Spacer(minLength: 0)
                    }
                    .padding(14)
                    .background(palette.surface, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
                    section("lock.shield", p.storedTitle, p.stored)
                    section("sparkles", p.aiTitle, p.ai)
                    section("bell.badge", p.notificationsTitle, p.notifications)
                    VStack(alignment: .leading, spacing: 8) {
                        Label(p.destinationsTitle, systemImage: "arrow.up.right.square").font(.subheadline.weight(.bold)).foregroundStyle(palette.ink)
                        if let destinations = disclosure?.destinations, !destinations.isEmpty {
                            ForEach(Array(destinations.enumerated()), id: \.offset) { _, destination in
                                VStack(alignment: .leading, spacing: 3) {
                                    Text(destination.kind == "ai" ? p.aiKind : destination.kind == "notification" ? p.notificationKind : p.integrationKind)
                                        .font(.caption2.weight(.semibold)).foregroundStyle(accent.color).textCase(.uppercase)
                                    Text(destination.name).font(.subheadline.weight(.semibold)).foregroundStyle(palette.ink)
                                    if !destination.host.isEmpty { Text(destination.host).font(.caption).foregroundStyle(palette.muted) }
                                    if !destination.capabilities.isEmpty {
                                        Text(destination.capabilities.map(p.capability).joined(separator: " · ")).font(.caption).foregroundStyle(palette.muted)
                                    }
                                }
                                .padding(12)
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .background(palette.surface, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                            }
                        } else if disclosure != nil {
                            Text(p.noDestinations).font(.footnote).foregroundStyle(palette.muted)
                        }
                    }
                    HStack(spacing: 20) {
                        if let policy = Brand.privacyPolicyURL { Button(p.policy) { openExternal(policy, failure: $linkFailure) } }
                        if let support = Brand.supportURL { Button(p.support) { openExternal(support, failure: $linkFailure) } }
                    }
                    .font(.footnote.weight(.semibold))
                    .foregroundStyle(accent.color)
                    .padding(.top, 4)
                    if !accepted { Text(p.consent).font(.footnote).foregroundStyle(palette.muted) }
                    if unavailable, !accepted { Text(p.unavailable).font(.footnote).foregroundStyle(palette.danger) }
                    if let error { Text(error).font(.footnote).foregroundStyle(palette.danger) }
                    Color.clear.frame(height: 1)
                        .onAppear { reachedEnd = true }
                }
                .padding(20)
                .frame(maxWidth: 760)
                .frame(maxWidth: .infinity)
            }
            .background(palette.canvas)
            .safeAreaInset(edge: .bottom) {
                VStack(spacing: 10) {
                    if !accepted {
                        PrimaryButton(label: p.accept, busy: busy == "accept", disabled: busy != nil || unavailable || !reachedEnd) { run("accept") }
                    }
                    Button {
                        if accepted { confirmWithdraw = true } else { run("decline") }
                    } label: {
                        ZStack {
                            Text(accepted ? p.withdraw : p.decline).font(.subheadline.weight(.semibold)).foregroundStyle(palette.danger).opacity(busy == "decline" ? 0 : 1)
                            if busy == "decline" { ProgressView().tint(palette.danger) }
                        }
                        .frame(maxWidth: .infinity, minHeight: 44)
                    }
                    .buttonStyle(.plain)
                    .disabled(busy != nil)
                }
                .padding(.horizontal, 20)
                .padding(.top, 12)
                .padding(.bottom, 8)
                .background(palette.surface)
                .overlay(alignment: .top) { Rectangle().fill(palette.line).frame(height: 0.5) }
            }
            .navigationTitle(p.title)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                if accepted {
                    ToolbarItem(placement: .topBarLeading) {
                        Button { model.leavePrivacy() } label: { Image(systemName: "chevron.left") }.disabled(busy != nil).accessibilityLabel(p.back)
                    }
                }
            }
            .confirmationDialog(p.withdrawTitle, isPresented: $confirmWithdraw, titleVisibility: .visible) {
                Button(p.withdraw, role: .destructive) { run("decline") }
                Button(p.cancel, role: .cancel) {}
            } message: { Text(p.withdrawBody) }
            .alert(item: $linkFailure) { Alert(title: Text($0.title)) }
        }
        .tint(accent.color)
    }

    private func section(_ symbol: String, _ title: String, _ body: String) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Label(title, systemImage: symbol).font(.subheadline.weight(.bold)).foregroundStyle(accent.palette.ink)
            Text(body).font(.footnote).foregroundStyle(accent.palette.muted)
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(accent.palette.surface, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
    }

    private func run(_ action: String) {
        guard busy == nil else { return }
        if action == "accept", accepted || (session.privacy?.version.isEmpty ?? true) { return }
        busy = action
        error = nil
        Task {
            do {
                if action == "accept" { try model.acceptPrivacy() } else { try await model.withdrawPrivacy() }
            } catch {
                self.error = PrivacyStrings.current.actionFailed
            }
            busy = nil
        }
    }
}
