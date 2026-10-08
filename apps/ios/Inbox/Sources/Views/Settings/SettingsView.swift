import SwiftUI

/// The portal's settings, as the web lays them out: the workspace catalogues
/// (teams, tags, saved replies, templates) and the person's own account.
struct SettingsView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.accent) private var accent
    @State private var availability: Availability = .away
    @State private var availabilityBusy = false
    @State private var confirmSignOut = false
    @State private var linkFailure: AppModel.AlertContent?

    var body: some View {
        let s = SettingsStrings.current
        let p = PrivacyStrings.current
        guard let session = model.session else { return AnyView(EmptyView()) }
        let server = model.server
        return AnyView(
            List {
                Section {
                    NavigationLink { TeamsScreen() } label: { Label(s.teams, systemImage: "person.3") }
                    NavigationLink { TagsScreen() } label: { Label(s.tags, systemImage: "tag") }
                    NavigationLink { CannedRepliesScreen() } label: { Label(s.canned, systemImage: "bolt") }
                    NavigationLink { TemplatesScreen() } label: { Label(s.templates, systemImage: "doc.text") }
                } header: { Text(s.workspace) }
                Section {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(session.userName.isEmpty ? session.branding.agencyName : session.userName).font(.body.weight(.semibold)).foregroundStyle(accent.palette.ink)
                        Text(session.branding.clientName).font(.caption).foregroundStyle(accent.palette.muted)
                    }
                    if session.userId != nil {
                        Button { Task { await toggleAvailability(server, session) } } label: {
                            HStack(spacing: 12) {
                                Circle().fill(availability == .online ? Theme.onlineGreen : accent.palette.subtle).frame(width: 10, height: 10)
                                Text(availability == .online ? Strings.current.inbox.online : Strings.current.inbox.away).foregroundStyle(accent.palette.ink)
                                Spacer()
                                if availabilityBusy { ProgressView().tint(accent.color) } else { Text(availability == .online ? WorkspaceStrings.current.goAway : WorkspaceStrings.current.goOnline).font(.footnote).foregroundStyle(accent.color) }
                            }
                        }
                        .disabled(availabilityBusy)
                    }
                    Button { model.showPrivacy() } label: { Label(p.title, systemImage: "checkmark.shield").foregroundStyle(accent.palette.ink) }
                    if let policy = Brand.privacyPolicyURL {
                        Button { openExternal(policy, failure: $linkFailure) } label: { Label(p.policy, systemImage: "arrow.up.right.square").foregroundStyle(accent.palette.ink) }
                    }
                    if let support = Brand.supportURL {
                        Button { openExternal(support, failure: $linkFailure) } label: { Label(p.support, systemImage: "questionmark.circle").foregroundStyle(accent.palette.ink) }
                    }
                    Button(role: .destructive) { confirmSignOut = true } label: { Label(s.signOut, systemImage: "rectangle.portrait.and.arrow.right") }
                } header: { Text(s.account) }
            }
            .listStyle(.insetGrouped)
            .navigationTitle(s.title)
            .task {
                if let me = try? await PortalAPI.members(server, session).first(where: { $0.id == session.userId }) { availability = me.availability }
            }
            .alert(Strings.current.inbox.signOutTitle, isPresented: $confirmSignOut) {
                Button(s.signOut, role: .destructive) { Task { await model.signOut() } }
                Button(s.cancel, role: .cancel) {}
            }
            .alert(item: $linkFailure) { Alert(title: Text($0.title)) }
        )
    }

    private func toggleAvailability(_ server: String, _ session: Session) async {
        guard !availabilityBusy else { return }
        availabilityBusy = true
        defer { availabilityBusy = false }
        if let result = try? await PortalAPI.setAvailability(server, session, availability == .online ? .away : .online) { availability = result.availability }
    }
}

struct TeamsScreen: View {
    @Environment(AppModel.self) private var model
    var body: some View {
        if let session = model.session {
            TeamsPanel(server: model.server, session: session)
                .navigationTitle(SettingsStrings.current.teams)
                .navigationBarTitleDisplayMode(.inline)
        }
    }
}

// MARK: Tags

struct TagsScreen: View {
    @Environment(AppModel.self) private var model
    @Environment(\.accent) private var accent
    @State private var tags: [ContactTag] = []
    @State private var loading = true
    @State private var error: String?
    @State private var editing: ContactTag?
    @State private var creating = false
    @State private var deleting: ContactTag?
    @State private var reload = 0

    var body: some View {
        let s = SettingsStrings.current
        guard let session = model.session else { return AnyView(EmptyView()) }
        let server = model.server
        let canManage = session.has("tags.manage")
        return AnyView(
            List {
                Section {
                    Text(canManage ? s.tagsHint : s.readOnly).font(.footnote).foregroundStyle(accent.palette.muted)
                    if let error { ErrorNotice(message: error, retryLabel: s.retry, retry: { reload += 1 }) }
                }
                Section {
                    if loading { ProgressView().frame(maxWidth: .infinity) }
                    else if tags.isEmpty { Text(s.noTags).foregroundStyle(accent.palette.muted) }
                    ForEach(tags) { tag in
                        Button { if canManage { editing = tag } } label: {
                            HStack(spacing: 12) {
                                Circle().fill(Color(hex: tag.color)).frame(width: 12, height: 12)
                                VStack(alignment: .leading, spacing: 3) {
                                    Text(tag.name).font(.body.weight(.semibold)).foregroundStyle(accent.palette.ink)
                                    let route = tag.routeTeamName ?? tag.routeAssigneeName
                                    Text("\(tag.contactCount) \(s.contacts)\(route.map { " · \(s.routesTo) \($0)" } ?? "")").font(.caption).foregroundStyle(accent.palette.muted)
                                }
                                Spacer()
                                if canManage { Image(systemName: "chevron.right").font(.footnote).foregroundStyle(accent.palette.subtle) }
                            }
                        }
                        .swipeActions { if canManage { Button(role: .destructive) { deleting = tag } label: { Label(s.delete, systemImage: "trash") } } }
                    }
                }
            }
            .navigationTitle(s.tags)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { if canManage { ToolbarItem(placement: .topBarTrailing) { Button { creating = true } label: { Image(systemName: "plus") }.accessibilityLabel(s.newTag) } } }
            .refreshable { reload += 1 }
            .task(id: reload) { await load(server, session) }
            .sheet(isPresented: $creating) { TagEditor(tag: nil, server: server, session: session) { reload += 1 } }
            .sheet(item: $editing) { tag in TagEditor(tag: tag, server: server, session: session) { reload += 1 } }
            .alert(s.deleteTag, isPresented: Binding(get: { deleting != nil }, set: { if !$0 { deleting = nil } })) {
                Button(s.delete, role: .destructive) { if let tag = deleting { Task { await delete(tag, server, session) } } }
                Button(s.cancel, role: .cancel) {}
            } message: { Text(s.deleteTagBody) }
        )
    }

    private func load(_ server: String, _ session: Session) async {
        do { tags = try await PortalAPI.tags(server, session); error = nil }
        catch is CancellationError { return }
        catch { self.error = (error as? APIError)?.message ?? SettingsStrings.current.loadFailed }
        loading = false
    }

    private func delete(_ tag: ContactTag, _ server: String, _ session: Session) async {
        do { try await PortalAPI.deleteTag(server, session, id: tag.id); tags.removeAll { $0.id == tag.id } }
        catch { self.error = (error as? APIError)?.message ?? SettingsStrings.current.saveFailed }
        deleting = nil
    }
}

struct TagEditor: View {
    let tag: ContactTag?
    let server: String
    let session: Session
    let onSaved: () -> Void
    @Environment(\.dismiss) private var dismiss
    @Environment(\.accent) private var accent
    @State private var name: String
    @State private var color: String
    @State private var busy = false
    @State private var error: String?

    static let colors = ["#6b7280", "#ef4444", "#f97316", "#eab308", "#22c55e", "#14b8a6", "#3b82f6", "#8b5cf6", "#ec4899"]

    init(tag: ContactTag?, server: String, session: Session, onSaved: @escaping () -> Void) {
        self.tag = tag
        self.server = server
        self.session = session
        self.onSaved = onSaved
        _name = State(initialValue: tag?.name ?? "")
        _color = State(initialValue: tag?.color ?? TagEditor.colors[0])
    }

    var body: some View {
        let s = SettingsStrings.current
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 8) {
                    FieldLabel(text: s.tagName).padding(.top, 12)
                    FormTextField(text: $name, disabled: busy, autocapitalize: .words, accessibilityLabel: s.tagName)
                    FieldLabel(text: s.tagColor).padding(.top, 12)
                    HStack(spacing: 10) {
                        ForEach(TagEditor.colors, id: \.self) { value in
                            Button { color = value } label: {
                                Circle().fill(Color(hex: value)).frame(width: 30, height: 30)
                                    .overlay(Circle().strokeBorder(accent.palette.ink, lineWidth: color == value ? 2 : 0))
                            }
                            .accessibilityLabel(value)
                        }
                    }
                    if let error { Text(error).foregroundStyle(accent.palette.danger) }
                    PrimaryButton(label: s.save, busy: busy, disabled: name.trimmingCharacters(in: .whitespaces).isEmpty) { Task { await save() } }.padding(.top, 20)
                }
                .padding(22)
            }
            .background(accent.palette.surface)
            .navigationTitle(tag == nil ? s.newTag : s.editTag)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .topBarLeading) { Button(s.cancel) { dismiss() }.disabled(busy) } }
        }
        .tint(accent.color)
        .presentationDetents([.medium, .large])
    }

    private func save() async {
        busy = true
        error = nil
        defer { busy = false }
        let trimmed = name.trimmingCharacters(in: .whitespaces)
        do {
            if let tag { _ = try await PortalAPI.updateTag(server, session, id: tag.id, ContactTagUpdate(name: trimmed, color: color)) }
            else { _ = try await PortalAPI.createTag(server, session, ContactTagCreate(name: trimmed, color: color)) }
            onSaved()
            dismiss()
        } catch let failure as APIError {
            error = failure.status == 409 ? SettingsStrings.current.duplicate : failure.message
        } catch { self.error = SettingsStrings.current.saveFailed }
    }
}

// MARK: Saved replies

struct CannedRepliesScreen: View {
    @Environment(AppModel.self) private var model
    @Environment(\.accent) private var accent
    @State private var items: [CannedReply] = []
    @State private var loading = true
    @State private var error: String?
    @State private var editing: CannedReply?
    @State private var creating = false
    @State private var deleting: CannedReply?
    @State private var reload = 0

    var body: some View {
        let s = SettingsStrings.current
        guard let session = model.session else { return AnyView(EmptyView()) }
        let server = model.server
        let canManage = session.has("canned.manage")
        return AnyView(
            List {
                Section {
                    Text(canManage ? s.cannedHint : s.readOnly).font(.footnote).foregroundStyle(accent.palette.muted)
                    if let error { ErrorNotice(message: error, retryLabel: s.retry, retry: { reload += 1 }) }
                }
                Section {
                    if loading { ProgressView().frame(maxWidth: .infinity) }
                    else if items.isEmpty { Text(s.noCanned).foregroundStyle(accent.palette.muted) }
                    ForEach(items) { item in
                        Button { if canManage { editing = item } } label: {
                            VStack(alignment: .leading, spacing: 4) {
                                Text("/\(item.shortcut)").font(.body.weight(.semibold)).foregroundStyle(accent.color)
                                Text(item.content).font(.subheadline).foregroundStyle(accent.palette.ink).lineLimit(3)
                            }
                        }
                        .swipeActions { if canManage { Button(role: .destructive) { deleting = item } label: { Label(s.delete, systemImage: "trash") } } }
                    }
                }
            }
            .navigationTitle(s.canned)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { if canManage { ToolbarItem(placement: .topBarTrailing) { Button { creating = true } label: { Image(systemName: "plus") }.accessibilityLabel(s.newReply) } } }
            .refreshable { reload += 1 }
            .task(id: reload) { await load(server, session) }
            .sheet(isPresented: $creating) { CannedReplyEditor(reply: nil, server: server, session: session) { reload += 1 } }
            .sheet(item: $editing) { item in CannedReplyEditor(reply: item, server: server, session: session) { reload += 1 } }
            .alert(s.deleteReply, isPresented: Binding(get: { deleting != nil }, set: { if !$0 { deleting = nil } })) {
                Button(s.delete, role: .destructive) { if let item = deleting { Task { await delete(item, server, session) } } }
                Button(s.cancel, role: .cancel) {}
            } message: { Text(s.deleteReplyBody) }
        )
    }

    private func load(_ server: String, _ session: Session) async {
        do { items = try await PortalAPI.cannedReplies(server, session); error = nil }
        catch is CancellationError { return }
        catch { self.error = (error as? APIError)?.message ?? SettingsStrings.current.loadFailed }
        loading = false
    }

    private func delete(_ item: CannedReply, _ server: String, _ session: Session) async {
        do { try await PortalAPI.deleteCannedReply(server, session, id: item.id); items.removeAll { $0.id == item.id } }
        catch { self.error = (error as? APIError)?.message ?? SettingsStrings.current.saveFailed }
        deleting = nil
    }
}

struct CannedReplyEditor: View {
    let reply: CannedReply?
    let server: String
    let session: Session
    let onSaved: () -> Void
    @Environment(\.dismiss) private var dismiss
    @Environment(\.accent) private var accent
    @State private var shortcut: String
    @State private var content: String
    @State private var busy = false
    @State private var error: String?

    init(reply: CannedReply?, server: String, session: Session, onSaved: @escaping () -> Void) {
        self.reply = reply
        self.server = server
        self.session = session
        self.onSaved = onSaved
        _shortcut = State(initialValue: reply?.shortcut ?? "")
        _content = State(initialValue: reply?.content ?? "")
    }

    private var valid: Bool {
        shortcut.range(of: "^[a-z0-9_-]{1,60}$", options: .regularExpression) != nil && !content.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    var body: some View {
        let s = SettingsStrings.current
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 8) {
                    FieldLabel(text: s.shortcut).padding(.top, 12)
                    HStack(spacing: 6) {
                        Text("/").font(.title3).foregroundStyle(accent.palette.muted)
                        FormTextField(text: $shortcut, placeholder: "saludo", disabled: busy, autocapitalize: .never, accessibilityLabel: s.shortcut)
                    }
                    Text(s.shortcutHint).font(.footnote).foregroundStyle(accent.palette.muted)
                    FieldLabel(text: s.content).padding(.top, 12)
                    FormTextField(text: $content, multiline: true, disabled: busy, accessibilityLabel: s.content)
                    Text(s.variablesHint).font(.footnote).foregroundStyle(accent.palette.muted)
                    if let error { Text(error).foregroundStyle(accent.palette.danger) }
                    PrimaryButton(label: s.save, busy: busy, disabled: !valid) { Task { await save() } }.padding(.top, 20)
                }
                .padding(22)
            }
            .scrollDismissesKeyboard(.interactively)
            .background(accent.palette.surface)
            .navigationTitle(reply == nil ? s.newReply : s.editReply)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .topBarLeading) { Button(s.cancel) { dismiss() }.disabled(busy) } }
        }
        .tint(accent.color)
    }

    private func save() async {
        busy = true
        error = nil
        defer { busy = false }
        let text = content.trimmingCharacters(in: .whitespacesAndNewlines)
        do {
            if let reply { _ = try await PortalAPI.updateCannedReply(server, session, id: reply.id, CannedReplyUpdate(shortcut: shortcut, content: text)) }
            else { _ = try await PortalAPI.createCannedReply(server, session, CannedReplyCreate(shortcut: shortcut, content: text)) }
            onSaved()
            dismiss()
        } catch let failure as APIError {
            error = failure.status == 409 ? SettingsStrings.current.duplicate : failure.message
        } catch { self.error = SettingsStrings.current.saveFailed }
    }
}

// MARK: WhatsApp templates

struct TemplatesScreen: View {
    @Environment(AppModel.self) private var model
    @Environment(\.accent) private var accent
    @State private var items: [Template] = []
    @State private var loading = true
    @State private var error: String?
    @State private var creating = false
    @State private var deleting: Template?
    @State private var reload = 0

    var body: some View {
        let s = SettingsStrings.current
        guard let session = model.session else { return AnyView(EmptyView()) }
        let server = model.server
        let canManage = session.has("templates.manage")
        return AnyView(
            List {
                Section {
                    Text(canManage ? s.templatesHint : s.readOnly).font(.footnote).foregroundStyle(accent.palette.muted)
                    if let error { ErrorNotice(message: error, retryLabel: s.retry, retry: { reload += 1 }) }
                }
                Section {
                    if loading { ProgressView().frame(maxWidth: .infinity) }
                    else if items.isEmpty { Text(s.noTemplates).foregroundStyle(accent.palette.muted) }
                    ForEach(items, id: \.listId) { item in
                        VStack(alignment: .leading, spacing: 5) {
                            HStack {
                                Text(item.name).font(.body.weight(.semibold)).foregroundStyle(accent.palette.ink)
                                Spacer()
                                Text(s.status(item.status)).font(.caption2.weight(.semibold))
                                    .foregroundStyle(item.status == "APPROVED" ? Theme.resolvedGreen : item.status == "REJECTED" ? accent.palette.danger : accent.palette.muted)
                                    .padding(.horizontal, 7).padding(.vertical, 3)
                                    .background((item.status == "APPROVED" ? Theme.resolvedGreen : accent.palette.muted).opacity(0.12), in: Capsule())
                            }
                            Text("\(item.language) · \(item.category.capitalized)").font(.caption).foregroundStyle(accent.palette.muted)
                            Text(item.body).font(.subheadline).foregroundStyle(accent.palette.ink).lineLimit(4)
                            if let reason = item.rejectedReason, !reason.isEmpty { Text(reason).font(.caption).foregroundStyle(accent.palette.danger) }
                        }
                        .padding(.vertical, 4)
                        .swipeActions { if canManage { Button(role: .destructive) { deleting = item } label: { Label(s.delete, systemImage: "trash") } } }
                    }
                }
            }
            .navigationTitle(s.templates)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { if canManage { ToolbarItem(placement: .topBarTrailing) { Button { creating = true } label: { Image(systemName: "plus") }.accessibilityLabel(s.newTemplate) } } }
            .refreshable { reload += 1 }
            .task(id: reload) { await load(server, session) }
            .sheet(isPresented: $creating) { TemplateEditorView(server: server, session: session) { reload += 1 } }
            .alert(s.deleteTemplate, isPresented: Binding(get: { deleting != nil }, set: { if !$0 { deleting = nil } })) {
                Button(s.delete, role: .destructive) { if let item = deleting { Task { await delete(item, server, session) } } }
                Button(s.cancel, role: .cancel) {}
            } message: { Text(s.deleteTemplateBody) }
        )
    }

    private func load(_ server: String, _ session: Session) async {
        do { items = try await PortalAPI.templates(server, session); error = nil }
        catch is CancellationError { return }
        catch {
            let api = error as? APIError
            self.error = api?.status == 404 || api?.status == 400 ? SettingsStrings.current.noLine : api?.message ?? SettingsStrings.current.loadFailed
        }
        loading = false
    }

    private func delete(_ item: Template, _ server: String, _ session: Session) async {
        do { try await PortalAPI.deleteTemplate(server, session, name: item.name); items.removeAll { $0.name == item.name } }
        catch { self.error = (error as? APIError)?.message ?? SettingsStrings.current.saveFailed }
        deleting = nil
    }
}
