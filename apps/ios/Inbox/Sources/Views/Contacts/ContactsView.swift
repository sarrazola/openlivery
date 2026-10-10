import SwiftUI

/// A native contact directory sharing the portal's contact and case records.
struct ContactsView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.accent) private var accent
    @State private var store = ContactsStore()
    @State private var panel: Panel?

    enum Panel: Identifiable, Equatable {
        case contact, new, edit, start, tags
        var id: Self { self }
    }

    var body: some View {
        let s = ContactsStrings.current
        guard let session = model.session else { return AnyView(EmptyView()) }
        let server = model.server
        return AnyView(
            VStack(spacing: 0) {
                HStack(spacing: 12) {
                    VStack(alignment: .leading, spacing: 3) {
                        Text(s.title).font(.system(size: 28, weight: .bold)).foregroundStyle(accent.palette.ink)
                        Text(s.subtitle).font(.footnote).foregroundStyle(accent.palette.muted)
                    }
                    Spacer()
                    Button { store.detailError = nil; panel = .new } label: {
                        Image(systemName: "person.badge.plus").font(.system(size: 20)).foregroundStyle(accent.color).frame(width: 44, height: 44)
                            .background(accent.tint(), in: RoundedRectangle(cornerRadius: 14, style: .continuous))
                    }
                    .accessibilityLabel(s.newContact)
                }
                .padding(18)
                SearchField(text: $store.search, placeholder: s.search).padding(.horizontal, 20).padding(.bottom, 12)
                if let error = store.error {
                    ErrorNotice(message: error, retryLabel: s.retry, retry: { Task { await store.load(server, session) } }).padding(.horizontal, 16).padding(.bottom, 8)
                }
                List {
                    if store.items.isEmpty, store.loading {
                        ContactsSkeleton(label: Strings.current.inbox.loading)
                            .listRowInsets(EdgeInsets())
                            .listRowSeparator(.hidden).listRowBackground(accent.palette.surface)
                    } else if store.items.isEmpty {
                        VStack(spacing: 14) {
                            Image(systemName: "person.2").font(.system(size: 46)).foregroundStyle(accent.palette.subtle)
                            Text(store.query.isEmpty ? s.empty : s.noMatches).font(.title3.weight(.semibold)).foregroundStyle(accent.palette.ink).multilineTextAlignment(.center)
                            if store.query.isEmpty { Text(s.emptyHint).font(.subheadline).foregroundStyle(accent.palette.muted).multilineTextAlignment(.center) }
                        }
                        .frame(maxWidth: .infinity).padding(30)
                        .listRowSeparator(.hidden).listRowBackground(accent.palette.surface)
                    }
                    ForEach(store.items) { item in
                        Button { panel = .contact; Task { await store.open(item, server, session) } } label: {
                            HStack(spacing: 12) {
                                Avatar(name: store.name(item), fontSize: 20)
                                VStack(alignment: .leading, spacing: 4) {
                                    Text(store.name(item)).font(.body.weight(.semibold)).foregroundStyle(accent.palette.ink).lineLimit(1)
                                    let line = [DialCodes.format(item.phone), item.email ?? ""].filter { !$0.isEmpty }.joined(separator: " · ")
                                    if !line.isEmpty { Text(line).font(.caption).foregroundStyle(accent.palette.muted).lineLimit(1) }
                                    Text("\(item.conversationCount) \(item.conversationCount == 1 ? s.conversation : s.conversations)\(item.openCount > 0 ? " · \(item.openCount) \(item.openCount == 1 ? s.openCase : s.openCases)" : "")")
                                        .font(.caption).foregroundStyle(accent.palette.muted)
                                }
                                Spacer()
                                Image(systemName: "chevron.right").font(.footnote).foregroundStyle(accent.palette.subtle)
                            }
                            .padding(.vertical, 12)
                            .contentShape(Rectangle())
                        }
                        .buttonStyle(.plain)
                        .listRowBackground(accent.palette.surface)
                        .onAppear { if item.id == store.items.last?.id { Task { await store.loadMore(server, session) } } }
                    }
                    if store.loadingMore {
                        HStack { Spacer(); ProgressView().tint(accent.color); Spacer() }.listRowSeparator(.hidden).listRowBackground(accent.palette.surface)
                    }
                }
                .listStyle(.plain)
                .scrollContentBackground(.hidden)
                .scrollDismissesKeyboard(.immediately)
                .refreshable { await store.load(server, session) }
            }
            .background(accent.palette.surface)
            .toolbar(.hidden, for: .navigationBar)
            .task(id: store.query) {
                store.onExpired = { model.expireSession() }
                if !store.query.isEmpty { try? await Task.sleep(for: .milliseconds(300)) }
                guard !Task.isCancelled else { return }
                await store.load(server, session)
            }
            .sheet(item: $panel) { which in
                ContactPanel(panel: which, store: store, server: server, session: session, onClose: { panel = nil }, onPanel: { panel = $0 }) { conversation in
                    panel = nil
                    model.openConversation(conversation)
                }
                .presentationDetents([.large])
                .interactiveDismissDisabled(store.busy)
            }
        )
    }
}

/// The modal that shows, creates, edits a contact or starts a conversation.
struct ContactPanel: View {
    let panel: ContactsView.Panel
    @Bindable var store: ContactsStore
    let server: String
    let session: Session
    let onClose: () -> Void
    let onPanel: (ContactsView.Panel) -> Void
    let onOpen: (Conversation) -> Void
    @Environment(\.accent) private var accent

    var body: some View {
        let s = ContactsStrings.current
        let title = panel == .new ? s.newContact : panel == .edit ? s.edit : panel == .start ? s.start : panel == .tags ? s.editTags : store.selected.map(store.name) ?? ""
        NavigationStack {
            Group {
                switch panel {
                case .new, .edit:
                    ContactEditor(contact: panel == .edit ? store.selected : nil, busy: store.busy) { patch in
                        Task { await store.save(patch, creating: panel == .new, server, session) { onPanel(.contact) } }
                    }
                case .contact:
                    contactDetail
                case .start:
                    if let contact = store.selected {
                        StartConversationView(contact: contact, channels: store.channels, history: store.history, server: server, session: session, onOpen: onOpen)
                    }
                case .tags:
                    if let contact = store.selected {
                        ContactTagsPicker(contact: contact, server: server, session: session) { updated in
                            store.selected = updated
                            onPanel(.contact)
                        }
                    }
                }
            }
            .background(accent.palette.surface)
            .navigationTitle(title)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button(panel == .edit || panel == .start || panel == .tags ? s.back : s.close) {
                        if panel == .edit || panel == .start || panel == .tags { store.detailError = nil; onPanel(.contact) } else { onClose() }
                    }
                    .disabled(store.busy)
                }
            }
        }
        .tint(accent.color)
    }

    @ViewBuilder
    private var contactDetail: some View {
        let s = ContactsStrings.current
        ScrollView {
            if let selected = store.selected {
                VStack(alignment: .leading, spacing: 0) {
                    if let error = store.detailError {
                        ErrorNotice(message: error, retryLabel: s.retry, retry: { Task { await store.open(selected, server, session) } }).padding(.bottom, 12)
                    }
                    VStack(spacing: 8) {
                        Avatar(name: store.name(selected), size: 80, radius: 28, fontSize: 34)
                        Text(store.name(selected)).font(.system(size: 28, weight: .bold)).foregroundStyle(accent.palette.ink).multilineTextAlignment(.center)
                        if let phone = selected.phone, !phone.isEmpty { Text(DialCodes.format(phone)).foregroundStyle(accent.palette.muted).textSelection(.enabled) }
                        if let email = selected.email, !email.isEmpty { Text(email).foregroundStyle(accent.palette.muted).textSelection(.enabled) }
                    }
                    .frame(maxWidth: .infinity).padding(.vertical, 16)
                    HStack(spacing: 10) {
                        actionTile(s.edit, "square.and.pencil", disabled: store.detailLoading || store.busy) { store.detailError = nil; onPanel(.edit) }
                        actionTile(s.start, "ellipsis.bubble", disabled: store.detailLoading || (selected.phone ?? "").isEmpty || store.channels.isEmpty) { store.detailError = nil; onPanel(.start) }
                    }
                    .padding(.vertical, 18)
                    if (selected.phone ?? "").isEmpty { Text(s.noPhone).font(.footnote).foregroundStyle(accent.palette.muted) }
                    if !store.detailLoading, !(selected.phone ?? "").isEmpty, store.channels.isEmpty { Text(s.noLine).font(.footnote).foregroundStyle(accent.palette.muted) }
                    HStack {
                        Text(s.tags).font(.title3.weight(.semibold)).foregroundStyle(accent.palette.ink)
                        Spacer()
                        Button(s.editTags) { store.detailError = nil; onPanel(.tags) }.font(.subheadline.weight(.semibold)).foregroundStyle(accent.color).disabled(store.detailLoading || store.busy)
                    }
                    .padding(.top, 24).padding(.bottom, 12)
                    if let tags = selected.tags, !tags.isEmpty {
                        FlowLayout(spacing: 8) {
                            ForEach(tags) { tag in
                                HStack(spacing: 6) {
                                    Circle().fill(Color(hex: tag.color)).frame(width: 8, height: 8)
                                    Text(tag.name).font(.caption.weight(.semibold)).foregroundStyle(accent.palette.ink)
                                }
                                .padding(.horizontal, 10).padding(.vertical, 6)
                                .background(accent.palette.canvas, in: Capsule())
                            }
                        }
                    } else {
                        Text(s.noTags).foregroundStyle(accent.palette.muted)
                    }
                    Text(s.notes).font(.title3.weight(.semibold)).foregroundStyle(accent.palette.ink).padding(.top, 24).padding(.bottom, 12)
                    Text(selected.notes.isEmpty ? s.noNotes : selected.notes).foregroundStyle(selected.notes.isEmpty ? accent.palette.muted : accent.palette.ink).textSelection(.enabled)
                    Text(s.history).font(.title3.weight(.semibold)).foregroundStyle(accent.palette.ink).padding(.top, 24).padding(.bottom, 12)
                    if store.detailLoading {
                        ProgressView().tint(accent.color)
                    } else if store.history.isEmpty {
                        Text(s.noHistory).foregroundStyle(accent.palette.muted)
                    } else {
                        ForEach(store.history) { conversation in
                            Button { onOpen(conversation) } label: {
                                VStack(alignment: .leading, spacing: 10) {
                                    HStack {
                                        Text(conversation.status == .resolved ? s.resolved : conversation.mode == .ai ? s.ai : s.human)
                                            .font(.caption2.weight(.semibold)).foregroundStyle(conversation.status == .resolved ? accent.palette.muted : accent.color)
                                            .padding(.horizontal, 9).padding(.vertical, 5).background(accent.tint(0.08), in: RoundedRectangle(cornerRadius: 7))
                                        Spacer()
                                        Text(When.shortDate(conversation.createdAt)).font(.caption).foregroundStyle(accent.palette.muted)
                                    }
                                    Text(conversation.preview.isEmpty ? s.noMessages : conversation.preview).foregroundStyle(accent.palette.ink).lineLimit(2).multilineTextAlignment(.leading)
                                    HStack {
                                        Text(Conversations.channelLabel(conversation.channel)).font(.caption).foregroundStyle(accent.palette.muted)
                                        Spacer()
                                        Image(systemName: "arrow.right").foregroundStyle(accent.color)
                                    }
                                }
                                .padding(15)
                                .background(accent.palette.raised, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
                                .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).strokeBorder(accent.palette.line, lineWidth: 0.5))
                            }
                            .buttonStyle(.plain)
                            .padding(.bottom, 12)
                        }
                    }
                }
                .padding(22)
            }
        }
    }

    private func actionTile(_ label: String, _ symbol: String, disabled: Bool, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            VStack(spacing: 7) {
                Image(systemName: symbol).font(.system(size: 20))
                Text(label).font(.footnote.weight(.semibold)).multilineTextAlignment(.center)
            }
            .foregroundStyle(accent.color)
            .frame(maxWidth: .infinity, minHeight: 60)
            .padding(12)
            .background(accent.tint(), in: RoundedRectangle(cornerRadius: 14, style: .continuous))
        }
        .buttonStyle(.plain)
        .disabled(disabled)
        .opacity(disabled ? 0.4 : 1)
    }
}

/// Create or edit a contact's name, phone, email and notes.
struct ContactEditor: View {
    let contact: Contact?
    let busy: Bool
    let onSave: (ContactUpdate) -> Void
    @Environment(\.accent) private var accent
    @State private var name: String
    @State private var phone: String
    @State private var email: String
    @State private var notes: String
    @State private var error: String?

    init(contact: Contact?, busy: Bool, onSave: @escaping (ContactUpdate) -> Void) {
        self.contact = contact
        self.busy = busy
        self.onSave = onSave
        _name = State(initialValue: contact?.name ?? "")
        _phone = State(initialValue: (contact?.phone ?? "").filter(\.isNumber))
        _email = State(initialValue: contact?.email ?? "")
        _notes = State(initialValue: contact?.notes ?? "")
    }

    var body: some View {
        let s = ContactsStrings.current
        ScrollView {
            VStack(alignment: .leading, spacing: 8) {
                FieldLabel(text: s.name).padding(.top, 12)
                FormTextField(text: $name, disabled: busy, contentType: .name, autocapitalize: .words, accessibilityLabel: s.name)
                FieldLabel(text: s.phone).padding(.top, 12)
                PhoneField(phone: $phone, disabled: busy, accessibilityLabel: s.phone)
                FieldLabel(text: s.email).padding(.top, 12)
                FormTextField(text: $email, keyboard: .emailAddress, disabled: busy, contentType: .emailAddress, autocapitalize: .never, accessibilityLabel: s.email)
                FieldLabel(text: s.notes).padding(.top, 12)
                FormTextField(text: $notes, multiline: true, disabled: busy, accessibilityLabel: s.notes)
                Text(s.notesHint).font(.footnote).foregroundStyle(accent.palette.muted)
                if let error { Text(error).foregroundStyle(accent.palette.danger) }
                PrimaryButton(label: s.save, busy: busy) { submit() }.padding(.top, 20)
            }
            .padding(22)
        }
        .scrollDismissesKeyboard(.interactively)
    }

    private func submit() {
        let s = ContactsStrings.current
        let digits = phone.filter(\.isNumber)
        let trimmedPhone = phone.trimmingCharacters(in: .whitespaces)
        // Existing web contacts can have no phone; editing notes must still work.
        if contact == nil || !(contact?.phone ?? "").isEmpty || !trimmedPhone.isEmpty, digits.count < 7 || digits.count > 15 {
            error = s.invalidPhone
            return
        }
        let trimmedEmail = email.trimmingCharacters(in: .whitespaces)
        if !trimmedEmail.isEmpty, trimmedEmail.range(of: "^[^\\s@]+@[^\\s@]+\\.[^\\s@]+$", options: .regularExpression) == nil {
            error = s.invalidEmail
            return
        }
        error = nil
        onSave(ContactUpdate(
            name: name.trimmingCharacters(in: .whitespaces),
            phone: trimmedPhone.isEmpty ? nil : trimmedPhone,
            email: .some(trimmedEmail.isEmpty ? nil : trimmedEmail),
            notes: notes.trimmingCharacters(in: .whitespacesAndNewlines)
        ))
    }
}

/// Reaching out first: a free message on the bridge, an approved template on WhatsApp Business.
struct StartConversationView: View {
    let contact: Contact
    let channels: [PortalChannel]
    let history: [Conversation]
    let server: String
    let session: Session
    let onOpen: (Conversation) -> Void
    @Environment(\.accent) private var accent
    @State private var channel: String
    @State private var message = ""
    @State private var templates: [Template] = []
    @State private var draft: TemplateSendDraft?
    @State private var loading = false
    @State private var busy = false
    @State private var error: String?
    @State private var attempt = 0
    @State private var currentHistory: [Conversation]

    init(contact: Contact, channels: [PortalChannel], history: [Conversation], server: String, session: Session, onOpen: @escaping (Conversation) -> Void) {
        self.contact = contact
        self.channels = channels
        self.history = history
        self.server = server
        self.session = session
        self.onOpen = onOpen
        _channel = State(initialValue: channels.first?.channel ?? "")
        _currentHistory = State(initialValue: history)
    }

    private var approved: Bool { channel == "whatsapp_cloud" }
    private var supported: Bool { channels.first { $0.channel == channel }?.supportsTemplates ?? false }
    private var existing: Conversation? { currentHistory.first { $0.status == .open && $0.channel == channel } }
    private var contactValues: TemplateContactValues {
        TemplateContactValues(contactName: contact.name, contactPhone: (contact.phone ?? "").filter(\.isNumber), contactEmail: contact.email ?? "", agentName: session.userName)
    }

    private var valid: Bool {
        guard existing == nil, !busy else { return false }
        if approved { return draft?.isComplete ?? false }
        return !message.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    var body: some View {
        let s = ContactsStrings.current
        ScrollView {
            VStack(alignment: .leading, spacing: 8) {
                FieldLabel(text: s.chooseLine).padding(.top, 12)
                ForEach(channels, id: \.listId) { line in
                    ChoiceRow(label: line.channel == "whatsapp_cloud" ? "WhatsApp Business" : "WhatsApp",
                              subtitle: [line.displayName, line.phoneNumber].compactMap { $0 }.filter { !$0.isEmpty }.joined(separator: " · "),
                              selected: channel == line.channel, disabled: busy) { channel = line.channel }
                }
                if let existing {
                    Text(s.existing).font(.footnote).foregroundStyle(accent.palette.muted)
                    ActionRow(label: s.open, symbol: "bubble.left") { onOpen(existing) }
                } else {
                    Text(approved ? s.templateHint : s.startHint).font(.footnote).foregroundStyle(accent.palette.muted)
                    if approved {
                        FieldLabel(text: s.templates).padding(.top, 12)
                        if loading { ProgressView().tint(accent.color) }
                        else if templates.isEmpty { Text(s.noTemplates).foregroundStyle(accent.palette.muted) }
                        else {
                            ForEach(templates, id: \.listId) { row in
                                ChoiceRow(label: "\(row.name) · \(row.language)", subtitle: row.body, selected: draft?.template.listId == row.listId, disabled: busy) {
                                    draft = TemplateSendDraft(template: row, contact: contactValues)
                                }
                            }
                        }
                        if let draft { TemplateSendForm(draft: draft, disabled: busy).padding(.top, 8) }
                    } else {
                        FieldLabel(text: s.message).padding(.top, 12)
                        FormTextField(text: $message, multiline: true, disabled: busy, accessibilityLabel: s.message)
                    }
                    if let error {
                        Text(error).foregroundStyle(accent.palette.danger)
                        if approved, templates.isEmpty { Button(s.retry) { attempt += 1 }.foregroundStyle(accent.color).disabled(loading || busy).padding(.vertical, 12) }
                    }
                    PrimaryButton(label: s.send, busy: busy, disabled: !valid) { Task { await send() } }.padding(.top, 20)
                }
            }
            .padding(22)
        }
        .scrollDismissesKeyboard(.interactively)
        .task(id: "\(channel)|\(attempt)") {
            error = nil
            draft = nil
            templates = []
            guard approved, supported else { loading = false; return }
            loading = true
            do { templates = try await PortalAPI.templates(server, session).filter { $0.status == "APPROVED" } }
            catch { self.error = (error as? APIError)?.message ?? s.loadFailed }
            loading = false
        }
    }

    private func send() async {
        let s = ContactsStrings.current
        guard valid, let phone = contact.phone, !phone.isEmpty else { return }
        busy = true
        error = nil
        defer { busy = false }
        do {
            guard !approved || draft != nil else { return }
            let payload: ConversationStart = approved
                ? .whatsappCloud(template: draft!.payload)
                : .whatsapp(text: message.trimmingCharacters(in: .whitespacesAndNewlines))
            let conversation = try await PortalAPI.startConversation(server, session, contactId: contact.id, payload)
            onOpen(conversation.summary)
        } catch let failure as APIError {
            error = failure.message
            // Another operator may have started a case since this contact was opened.
            if failure.status == 409, let rows = try? await PortalAPI.contactConversations(server, session, id: contact.id) { currentHistory = rows }
        } catch {
            self.error = s.sendFailed
        }
    }
}

@MainActor
@Observable
final class ContactsStore {
    var items: [Contact] = []
    var search = ""
    var loading = true
    var loadingMore = false
    var hasMore = false
    var error: String?
    var selected: Contact?
    var history: [Conversation] = []
    var channels: [PortalChannel] = []
    var detailLoading = false
    var detailError: String?
    var busy = false
    var onExpired: (() -> Void)?

    private static let pageSize = 40
    private var generation = 0
    private var detailGeneration = 0
    private var offset = 0

    var query: String { search.trimmingCharacters(in: .whitespaces) }

    func name(_ contact: Contact) -> String {
        let trimmed = contact.name.trimmingCharacters(in: .whitespaces)
        if !trimmed.isEmpty { return trimmed }
        return contact.phone ?? contact.email ?? ContactsStrings.current.unnamed
    }

    private func message(_ error: Error, _ fallback: String) -> String {
        if let api = error as? APIError {
            if api.isUnauthorized { onExpired?() }
            return api.message
        }
        return fallback
    }

    func load(_ server: String, _ session: Session) async {
        generation += 1
        let current = generation
        loadingMore = false
        do {
            let rows = try await PortalAPI.contacts(server, session, search: query.isEmpty ? nil : query, limit: ContactsStore.pageSize, offset: 0)
            guard current == generation else { return }
            items = rows
            offset = rows.count
            hasMore = rows.count == ContactsStore.pageSize
            error = nil
        } catch is CancellationError {
        } catch {
            guard current == generation else { return }
            self.error = message(error, ContactsStrings.current.loadFailed)
        }
        if current == generation { loading = false }
    }

    func loadMore(_ server: String, _ session: Session) async {
        guard hasMore, !loadingMore, !loading else { return }
        loadingMore = true
        let current = generation
        defer { if current == generation { loadingMore = false } }
        do {
            let rows = try await PortalAPI.contacts(server, session, search: query.isEmpty ? nil : query, limit: ContactsStore.pageSize, offset: offset)
            guard current == generation else { return }
            var seen = Set(items.map(\.id))
            for row in rows where !seen.contains(row.id) { items.append(row); seen.insert(row.id) }
            offset += rows.count
            hasMore = rows.count == ContactsStore.pageSize
            error = nil
        } catch {
            guard current == generation else { return }
            self.error = message(error, ContactsStrings.current.loadFailed)
        }
    }

    func open(_ contact: Contact, _ server: String, _ session: Session) async {
        selected = contact
        history = []
        channels = []
        detailLoading = true
        detailError = nil
        detailGeneration += 1
        let current = detailGeneration
        defer { if current == detailGeneration { detailLoading = false } }
        do {
            async let fresh = PortalAPI.contact(server, session, id: contact.id)
            async let rows = PortalAPI.contactConversations(server, session, id: contact.id)
            async let lines = PortalAPI.channels(server, session)
            let (contactRow, historyRows, channelRows) = try await (fresh, rows, lines)
            guard current == detailGeneration else { return }
            selected = contactRow
            history = historyRows
            channels = channelRows.filter { InboxRules.isWhatsApp($0.channel) }
        } catch {
            guard current == detailGeneration else { return }
            detailError = message(error, ContactsStrings.current.loadFailed)
        }
    }

    func save(_ patch: ContactUpdate, creating: Bool, _ server: String, _ session: Session, done: () -> Void) async {
        guard !busy else { return }
        busy = true
        detailError = nil
        defer { busy = false }
        do {
            let saved: Contact
            if creating {
                var email: String?
                if case .some(let value) = patch.email { email = value }
                saved = try await PortalAPI.createContact(server, session, ContactCreate(name: patch.name, phone: patch.phone ?? "", email: email, notes: patch.notes))
            } else if let selected {
                saved = try await PortalAPI.updateContact(server, session, id: selected.id, patch)
            } else { return }
            self.selected = saved
            done()
            await load(server, session)
            await open(saved, server, session)
        } catch {
            if let api = error as? APIError, api.status == 409 { detailError = ContactsStrings.current.duplicatePhone }
            else { detailError = message(error, ContactsStrings.current.saveFailed) }
        }
    }
}

/// Pick which of the workspace's tags this contact carries.
struct ContactTagsPicker: View {
    let contact: Contact
    let server: String
    let session: Session
    let onSaved: (Contact) -> Void
    @Environment(\.accent) private var accent
    @State private var tags: [ContactTag] = []
    @State private var chosen: Set<String>
    @State private var loading = true
    @State private var busy = false
    @State private var error: String?

    init(contact: Contact, server: String, session: Session, onSaved: @escaping (Contact) -> Void) {
        self.contact = contact
        self.server = server
        self.session = session
        self.onSaved = onSaved
        _chosen = State(initialValue: Set((contact.tags ?? []).map(\.id)))
    }

    var body: some View {
        let s = ContactsStrings.current
        ScrollView {
            VStack(alignment: .leading, spacing: 8) {
                if loading {
                    ProgressView().tint(accent.color).frame(maxWidth: .infinity).padding(24)
                } else if tags.isEmpty {
                    Text(s.noTagsDefined).foregroundStyle(accent.palette.muted).padding(.top, 12)
                } else {
                    ForEach(tags) { tag in
                        Button { if chosen.contains(tag.id) { chosen.remove(tag.id) } else { chosen.insert(tag.id) } } label: {
                            HStack(spacing: 12) {
                                Image(systemName: chosen.contains(tag.id) ? "checkmark.square.fill" : "square").font(.system(size: 22)).foregroundStyle(accent.color)
                                Circle().fill(Color(hex: tag.color)).frame(width: 10, height: 10)
                                Text(tag.name).font(.body.weight(.semibold)).foregroundStyle(accent.palette.ink)
                                Spacer()
                            }
                            .padding(12)
                            .background(accent.palette.surface, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                            .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).strokeBorder(accent.palette.line, lineWidth: 1))
                        }
                        .buttonStyle(.plain)
                        .disabled(busy)
                    }
                }
                if let error { Text(error).foregroundStyle(accent.palette.danger) }
                if !tags.isEmpty { PrimaryButton(label: s.done, busy: busy) { Task { await save() } }.padding(.top, 20) }
            }
            .padding(22)
        }
        .task {
            do { tags = try await PortalAPI.tags(server, session) }
            catch { self.error = (error as? APIError)?.message ?? s.loadFailed }
            loading = false
        }
    }

    private func save() async {
        busy = true
        error = nil
        defer { busy = false }
        do {
            let updated = try await PortalAPI.setContactTags(server, session, id: contact.id, tagIds: tags.map(\.id).filter { chosen.contains($0) })
            onSaved(updated)
        } catch {
            self.error = (error as? APIError)?.message ?? ContactsStrings.current.saveFailed
        }
    }
}
