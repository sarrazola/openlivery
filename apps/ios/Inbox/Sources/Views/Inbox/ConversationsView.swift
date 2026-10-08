import SwiftUI

/// The inbox: open and resolved cases, folders, search, team and channel filters.
struct ConversationsView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.accent) private var accent
    @Environment(\.scenePhase) private var scenePhase
    @State private var store = ConversationsStore()
    @State private var sheet: Sheet?
    @State private var confirmSignOut = false
    @State private var linkFailure: AppModel.AlertContent?

    private enum Sheet: String, Identifiable { case filters, account; var id: String { rawValue } }
    private static let pageSize = 40

    var body: some View {
        let s = Strings.current
        let palette = accent.palette
        guard let session = model.session else { return AnyView(EmptyView()) }
        let server = model.server
        let logo = PortalAPI.assetURL(server, session.branding.clientLogoUrl ?? session.branding.agencyLogoUrl)
        return AnyView(
            VStack(spacing: 0) {
                header(session: session, logo: logo)
                controls(session: session)
                if let error = store.error {
                    Button { Task { await store.load(server, session, reset: true) } } label: {
                        HStack {
                            Text(store.items.isEmpty ? error : s.inbox.connectionError).foregroundStyle(palette.danger).frame(maxWidth: .infinity, alignment: .leading)
                            Text(s.inbox.retry).fontWeight(.bold).foregroundStyle(palette.danger)
                        }
                        .padding(12)
                        .background(Theme.tint("#d95757"), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
                    }
                    .buttonStyle(.plain)
                    .padding(.horizontal, 16)
                    .padding(.bottom, 8)
                }
                if !store.loaded {
                    Spacer()
                    ProgressView().tint(accent.color)
                    Spacer()
                } else {
                    list(server: server, session: session)
                }
            }
            .background(palette.surface)
            .toolbar(.hidden, for: .navigationBar)
            .task(id: store.filterKey) {
                store.onExpired = { model.expireSession() }
                store.openConversation = { model.inboxPath.last?.id ?? model.contactsPath.last?.id }
                LocalAlerts.shared.requestPermissionIfNeeded()
                await store.start(server, session)
            }
            .onChange(of: scenePhase) { _, phase in
                if phase == .active { Task { await store.load(server, session, reset: true) } }
            }
            .onChange(of: model.inboxPath.count) { old, new in
                if new < old { Task { await store.load(server, session, reset: true) } }
            }
            .sheet(item: $sheet) { which in
                switch which {
                case .filters: filtersSheet(session: session)
                case .account: accountSheet(server: server, session: session)
                }
            }
            .alert(s.inbox.signOutTitle, isPresented: $confirmSignOut) {
                Button(s.inbox.signOut, role: .destructive) { sheet = nil; Task { await model.signOut() } }
                Button(s.inbox.cancel, role: .cancel) {}
            }
            .alert(item: $linkFailure) { Alert(title: Text($0.title)) }
        )
    }

    private func header(session: Session, logo: URL?) -> some View {
        let s = Strings.current.inbox
        return HStack(spacing: 12) {
            if let logo {
                AsyncImage(url: logo) { image in image.resizable().scaledToFit() } placeholder: { Avatar(name: session.branding.clientName, size: 43, radius: 13) }
                    .frame(width: 43, height: 43)
                    .clipShape(RoundedRectangle(cornerRadius: 13, style: .continuous))
            } else {
                Avatar(name: session.branding.clientName, size: 43, radius: 13)
            }
            VStack(alignment: .leading, spacing: 2) {
                Text(session.branding.clientName).font(.caption).foregroundStyle(accent.palette.muted).lineLimit(1)
                Text(s.title).font(.system(size: 23, weight: .bold)).foregroundStyle(accent.palette.ink)
            }
            Spacer()
            Button { sheet = .account } label: {
                Image(systemName: "person.crop.circle").font(.system(size: 28)).foregroundStyle(accent.color).frame(width: 44, height: 44)
            }
            .accessibilityLabel(s.account)
        }
        .padding(.horizontal, 20)
        .padding(.top, 10)
        .padding(.bottom, 12)
        .overlay(alignment: .bottom) { Rectangle().fill(accent.palette.line).frame(height: 0.5) }
    }

    private func controls(session: Session) -> some View {
        let s = Strings.current.inbox
        return VStack(alignment: .leading, spacing: 12) {
            SearchField(text: $store.search, placeholder: s.search)
            HStack(spacing: 10) {
                Picker("", selection: $store.status) {
                    Text("\(s.open) \(store.summary.map { String($0.open) } ?? "")").tag(ConversationStatus.open)
                    Text("\(s.resolved) \(store.summary.map { String($0.resolved) } ?? "")").tag(ConversationStatus.resolved)
                }
                .pickerStyle(.segmented)
                .onChange(of: store.status) { _, _ in store.folder = .all }
                Button { sheet = .filters } label: {
                    Image(systemName: "slider.horizontal.3").foregroundStyle(accent.color)
                        .frame(width: 45, height: 36)
                        .background(store.filterActive ? accent.tint() : accent.palette.surface, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
                        .overlay(RoundedRectangle(cornerRadius: 10, style: .continuous).strokeBorder(store.filterActive ? accent.color : accent.palette.line, lineWidth: 1))
                }
                .accessibilityLabel(s.filters)
            }
            if store.status == .open {
                HStack(spacing: 8) {
                    ForEach(folders(session), id: \.self) { folder in
                        let count = folderCount(folder)
                        Pill(label: folderLabel(folder), count: count.map { $0 > 99 ? "99+" : String($0) }, expand: true, selected: store.folder == folder) { store.folder = folder }
                    }
                }
            }
            if !store.channel.isEmpty {
                Button { store.channel = "" } label: {
                    HStack(spacing: 6) {
                        Image(systemName: Conversations.channelSymbol(store.channel)).font(.caption)
                        Text(Conversations.channelName(store.channel)).font(.subheadline)
                        Image(systemName: "xmark").font(.caption)
                    }
                    .foregroundStyle(accent.color)
                }
                .accessibilityLabel(s.clearFilters)
            }
            if !store.team.isEmpty {
                Button { store.team = "" } label: {
                    HStack(spacing: 6) {
                        Image(systemName: "person.2").font(.caption)
                        Text(store.teams.first { $0.id == store.team }?.name ?? s.teams).font(.subheadline)
                        Image(systemName: "xmark").font(.caption)
                    }
                    .foregroundStyle(accent.color)
                }
            }
        }
        .padding(16)
        .padding(.bottom, -8)
    }

    private func folders(_ session: Session) -> [ConversationsStore.Folder] {
        session.userId == nil ? [.all, .unread, .ai] : [.all, .unread, .mine, .ai]
    }

    private func folderLabel(_ folder: ConversationsStore.Folder) -> String {
        let s = Strings.current.inbox
        switch folder {
        case .all: return s.all
        case .unread: return s.unread
        case .mine: return s.mine
        case .ai: return s.ai
        }
    }

    private func folderCount(_ folder: ConversationsStore.Folder) -> Int? {
        guard let summary = store.summary else { return nil }
        let value: Int
        switch folder {
        case .all: value = summary.open
        case .unread: value = summary.unread
        case .mine: value = summary.mine
        case .ai: value = summary.ai
        }
        return value > 0 ? value : nil
    }

    private func list(server: String, session: Session) -> some View {
        let s = Strings.current
        let filtered = !store.query.isEmpty || !store.team.isEmpty || !store.channel.isEmpty || store.folder != .all
        return List {
            if store.items.isEmpty {
                VStack(spacing: 8) {
                    Image(systemName: store.status == .resolved ? "checkmark.circle" : "bubble.left.and.bubble.right")
                        .font(.system(size: 30)).foregroundStyle(accent.color)
                        .padding(20).background(accent.tint(), in: RoundedRectangle(cornerRadius: 25, style: .continuous))
                        .padding(.bottom, 10)
                    Text(filtered ? s.inbox.noResults : s.list.emptyTitle).font(.headline).foregroundStyle(accent.palette.ink).multilineTextAlignment(.center)
                    Text(filtered ? s.inbox.noResultsBody : s.list.emptyBody).font(.subheadline).foregroundStyle(accent.palette.muted).multilineTextAlignment(.center)
                    if filtered { Button(s.inbox.clearFilters) { store.clearFilters() }.foregroundStyle(accent.color).fontWeight(.semibold).padding(.top, 8) }
                }
                .frame(maxWidth: .infinity)
                .padding(36)
                .listRowSeparator(.hidden)
                .listRowBackground(accent.palette.surface)
            }
            ForEach(store.items) { item in
                Button { model.openConversation(item) } label: { ConversationRow(item: item) }
                    .buttonStyle(.plain)
                    .listRowInsets(EdgeInsets(top: 0, leading: 0, bottom: 0, trailing: 0))
                    .listRowBackground(item.mode == .human && item.unreadCount > 0 ? accent.tint(0.035) : accent.palette.surface)
                    .alignmentGuide(.listRowSeparatorLeading) { _ in 83 }
                    .onAppear {
                        if item.id == store.items.last?.id, store.hasMore { Task { await store.load(server, session, append: true) } }
                    }
            }
            if store.hasMore {
                HStack { Spacer(); if store.loadingMore { ProgressView().tint(accent.color) } else { Text(s.inbox.loadMore).foregroundStyle(accent.color) }; Spacer() }
                    .frame(minHeight: 56)
                    .listRowSeparator(.hidden)
                    .listRowBackground(accent.palette.surface)
                    .onTapGesture { Task { await store.load(server, session, append: true) } }
            }
        }
        .listStyle(.plain)
        .scrollContentBackground(.hidden)
        .scrollDismissesKeyboard(.immediately)
        .refreshable { await store.load(server, session, reset: true) }
    }

    private func filtersSheet(session: Session) -> some View {
        let s = Strings.current.inbox
        return SheetScaffold(title: s.filters, onClose: { sheet = nil }) {
            Text(s.allChannels).font(.subheadline).foregroundStyle(accent.palette.muted).padding(.top, 4)
            ForEach(["", "whatsapp", "whatsapp_cloud", "instagram", "messenger", "widget"], id: \.self) { value in
                ActionRow(label: value.isEmpty ? s.allChannels : Conversations.channelName(value), selected: store.channel == value) { store.channel = value }
            }
            Text(s.teams).font(.subheadline).foregroundStyle(accent.palette.muted).padding(.top, 12)
            ActionRow(label: s.allTeams, selected: store.team.isEmpty) { store.team = ""; sheet = nil }
            ForEach(store.teams) { team in
                ActionRow(label: team.name, selected: store.team == team.id) { store.team = team.id; sheet = nil }
            }
        }
        .presentationDetents([.medium, .large])
    }

    private func accountSheet(server: String, session: Session) -> some View {
        let s = Strings.current.inbox
        let p = PrivacyStrings.current
        return SheetScaffold(title: s.account, onClose: { sheet = nil }) {
            Text(session.userName.isEmpty ? session.branding.agencyName : session.userName).font(.title3.weight(.semibold)).foregroundStyle(accent.palette.ink)
            Text(session.branding.clientName).foregroundStyle(accent.palette.muted).padding(.bottom, 8)
            if session.userId != nil {
                Button { Task { await store.toggleAvailability(server, session) } } label: {
                    HStack(spacing: 12) {
                        Circle().fill(store.availability == .online ? Theme.whatsappGreen : accent.palette.subtle).frame(width: 10, height: 10)
                        Text(store.availability == .online ? s.online : s.away).foregroundStyle(accent.palette.ink)
                        Spacer()
                        if store.availabilityBusy { ProgressView().tint(accent.color) } else { Image(systemName: "arrow.left.arrow.right").foregroundStyle(accent.color) }
                    }
                    .frame(minHeight: 56)
                }
                .buttonStyle(.plain)
                .disabled(store.availabilityBusy)
                Text(s.availabilityHint).font(.subheadline).foregroundStyle(accent.palette.muted)
            }
            Button { sheet = nil; model.showPrivacy() } label: {
                HStack(spacing: 12) { Image(systemName: "checkmark.shield").foregroundStyle(accent.color); Text(p.title).foregroundStyle(accent.palette.ink); Spacer() }.frame(minHeight: 56)
            }
            .buttonStyle(.plain)
            .padding(.top, 12)
            if let policy = Brand.privacyPolicyURL {
                Button { openExternal(policy, failure: $linkFailure) } label: {
                    HStack(spacing: 12) { Image(systemName: "arrow.up.right.square").foregroundStyle(accent.color); Text(p.policy).foregroundStyle(accent.palette.ink); Spacer() }.frame(minHeight: 56)
                }
                .buttonStyle(.plain)
            }
            if let support = Brand.supportURL {
                Button { openExternal(support, failure: $linkFailure) } label: {
                    HStack(spacing: 12) { Image(systemName: "arrow.up.right.square").foregroundStyle(accent.color); Text(p.support).foregroundStyle(accent.palette.ink); Spacer() }.frame(minHeight: 56)
                }
                .buttonStyle(.plain)
            }
            Button { confirmSignOut = true } label: {
                HStack(spacing: 12) { Image(systemName: "rectangle.portrait.and.arrow.right").foregroundStyle(accent.palette.danger); Text(s.signOut).foregroundStyle(accent.palette.danger); Spacer() }.frame(minHeight: 56)
            }
            .buttonStyle(.plain)
            .padding(.top, 12)
        }
        .presentationDetents([.medium, .large])
    }
}

/// One conversation in the list.
struct ConversationRow: View {
    let item: Conversation
    @Environment(\.accent) private var accent

    var body: some View {
        let s = Strings.current
        let name = Conversations.name(item)
        let unread = item.mode == .human && item.unreadCount > 0
        let owner = item.mode == .ai ? s.inbox.aiHandling : (item.assigneeName ?? s.inbox.legacyHuman)
        HStack(alignment: .top, spacing: 13) {
            Avatar(name: name)
                .overlay(alignment: .bottomTrailing) {
                    Image(systemName: Conversations.channelSymbol(item.channel))
                        .font(.system(size: 11, weight: .semibold))
                        .foregroundStyle(item.channel.hasPrefix("whatsapp") ? Theme.whatsappGreen : accent.palette.muted)
                        .padding(3)
                        .background(accent.palette.surface, in: Circle())
                        .offset(x: 4, y: 3)
                }
            VStack(alignment: .leading, spacing: 4) {
                HStack(spacing: 8) {
                    Text(name).font(.body.weight(unread ? .heavy : .semibold)).foregroundStyle(accent.palette.ink).lineLimit(1)
                    Spacer(minLength: 4)
                    Text(When.rowLabel(InboxRules.timestamp(item))).font(.caption2).foregroundStyle(unread ? accent.color : accent.palette.muted)
                }
                HStack(alignment: .top, spacing: 8) {
                    Text(item.preview.isEmpty ? s.list.noMessages : item.preview).font(.subheadline).foregroundStyle(unread ? accent.palette.ink : accent.palette.muted).lineLimit(2)
                    Spacer(minLength: 4)
                    if unread {
                        Text(item.unreadCount > 99 ? "99+" : String(item.unreadCount))
                            .font(.system(size: 10, weight: .bold)).foregroundStyle(.white)
                            .padding(.horizontal, 6).frame(minWidth: 20, minHeight: 20)
                            .background(accent.color, in: Capsule())
                    }
                }
                HStack(spacing: 4) {
                    Image(systemName: item.status == .resolved ? "checkmark.circle" : item.mode == .ai ? "sparkles" : "person")
                        .font(.system(size: 11)).foregroundStyle(accent.palette.muted)
                    Text((item.status == .resolved ? s.inbox.resolved : owner) + (item.teamName.map { " · \($0)" } ?? ""))
                        .font(.caption2).foregroundStyle(accent.palette.muted).lineLimit(1)
                    Spacer(minLength: 4)
                    Text(Conversations.channelLabel(item.channel)).font(.system(size: 10)).foregroundStyle(accent.palette.muted)
                }
                .padding(.top, 3)
            }
        }
        .padding(.horizontal, 20)
        .padding(.vertical, 14)
        .contentShape(Rectangle())
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(name), \(owner)\(unread ? ", \(s.inbox.unread)" : "")")
    }
}

/// Loads, filters, pages and polls the list.
@MainActor
@Observable
final class ConversationsStore {
    enum Folder: Hashable { case all, unread, mine, ai }

    var items: [Conversation] = []
    var summary: InboxSummary?
    var teams: [Team] = []
    var status: ConversationStatus = .open
    var folder: Folder = .all
    var team = ""
    var channel = ""
    var search = ""
    var availability: Availability = .away
    var availabilityBusy = false
    var loaded = false
    var loadingMore = false
    var hasMore = false
    var error: String?

    private static let pageSize = 40
    private var nextOffset = 0
    private var requestId = 0
    private var fetching = false
    private var pollTask: Task<Void, Never>?
    private var contextLoaded = false

    var query: String { search.trimmingCharacters(in: .whitespaces) }
    var filterActive: Bool { !team.isEmpty || !channel.isEmpty }
    /// Changing any of these restarts the list from the first page.
    var filterKey: String { "\(status.rawValue)|\(folder)|\(team)|\(channel)|\(query)" }

    func clearFilters() {
        search = ""
        folder = .all
        team = ""
        channel = ""
    }

    private func filters(limit: Int, offset: Int) -> PortalAPI.ConversationFilters {
        PortalAPI.ConversationFilters(
            status: status, mode: folder == .ai ? .ai : nil, assignee: folder == .mine ? "me" : nil, team: team.isEmpty ? nil : team,
            unread: folder == .unread, channel: channel.isEmpty ? nil : channel, search: query.isEmpty ? nil : query, limit: limit, offset: offset
        )
    }

    /// Runs for as long as the screen is on with this filter key.
    func start(_ server: String, _ session: Session) async {
        pollTask?.cancel()
        items = []
        loaded = false
        hasMore = false
        error = nil
        nextOffset = 0
        requestId += 1
        if !contextLoaded { await loadContext(server, session) }
        // Debounce typing: a search key change waits before hitting the server.
        if !query.isEmpty { try? await Task.sleep(for: .milliseconds(300)) }
        guard !Task.isCancelled else { return }
        await load(server, session, reset: true)
        guard !Task.isCancelled else { return }
        pollTask = Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(8))
                guard !Task.isCancelled, let self else { return }
                await self.load(server, session)
            }
        }
        await pollTask?.value
    }

    private func loadContext(_ server: String, _ session: Session) async {
        do {
            async let teamsRows = PortalAPI.teams(server, session)
            async let membersRows = PortalAPI.members(server, session)
            let (nextTeams, members) = try await (teamsRows, membersRows)
            teams = nextTeams
            if let me = members.first(where: { $0.id == session.userId }) { availability = me.availability }
            contextLoaded = true
        } catch let failure as APIError where failure.isUnauthorized {
            onExpired?()
        } catch {}
    }

    var onExpired: (() -> Void)?
    /// The thread on screen, which never rings for its own messages.
    var openConversation: () -> String? = { nil }

    func load(_ server: String, _ session: Session, append: Bool = false, reset: Bool = false) async {
        if fetching && !reset { return }
        requestId += 1
        let id = requestId
        fetching = true
        if append { loadingMore = true }
        defer {
            if id == requestId {
                fetching = false
                loaded = true
                loadingMore = false
            }
        }
        do {
            let offset = append ? nextOffset : 0
            let target = max(ConversationsStore.pageSize, nextOffset)
            // Refresh every loaded row so changed assignments and resolved cases disappear.
            let limit = append ? ConversationsStore.pageSize : min(target, 200)
            var rows = try await PortalAPI.listConversations(server, session, filters(limit: limit, offset: offset))
            var exhausted = rows.count < limit
            if !append, !exhausted, target > limit {
                while rows.count < target {
                    let nextLimit = min(200, target - rows.count)
                    let next = try await PortalAPI.listConversations(server, session, filters(limit: nextLimit, offset: rows.count))
                    rows.append(contentsOf: next)
                    exhausted = next.count < nextLimit
                    if exhausted { break }
                }
            }
            guard id == requestId else { return }
            nextOffset = offset + rows.count
            items = InboxRules.mergePages(append ? items : [], rows)
            hasMore = !exhausted
            error = nil
            // Only the unfiltered open list is a faithful picture of what needs a person.
            if status == .open, folder == .all, query.isEmpty, team.isEmpty, channel.isEmpty {
                LocalAlerts.shared.observe(items, session: session, openConversationId: openConversation())
            }
            if let next = try? await PortalAPI.inboxSummary(server, session), id == requestId { summary = next }
        } catch is CancellationError {
        } catch let failure as APIError {
            guard id == requestId else { return }
            if failure.isUnauthorized { onExpired?() } else { error = failure.message }
        } catch {
            guard id == requestId else { return }
            self.error = Strings.current.list.loadFailed
        }
    }

    func toggleAvailability(_ server: String, _ session: Session) async {
        guard !availabilityBusy else { return }
        availabilityBusy = true
        defer { availabilityBusy = false }
        do {
            let result = try await PortalAPI.setAvailability(server, session, availability == .online ? .away : .online)
            availability = result.availability
        } catch {
            self.error = error.localizedDescription
        }
    }
}
