import SwiftUI

/// The portal's case lifecycle and permissions, presented as a native thread.
struct ChatView: View {
    let conversation: Conversation
    @Environment(AppModel.self) private var model
    @Environment(\.accent) private var accent
    @Environment(\.scenePhase) private var scenePhase
    @Environment(\.dismiss) private var dismiss
    @State private var store: ChatStore
    @State private var sheet: Sheet?
    @State private var messageAction: Message?
    @State private var templateOpen = false
    @State private var confirmResolve = false
    @State private var insertedReply: String?
    @State private var now = Date()

    private enum Sheet: String, Identifiable { case details, assignee, team, media, canned; var id: String { rawValue } }

    init(conversation: Conversation) {
        self.conversation = conversation
        _store = State(initialValue: ChatStore(conversation: conversation))
    }

    var body: some View {
        let c = ChatStrings.current
        guard let session = model.session else { return AnyView(EmptyView()) }
        let server = model.server
        let detail = store.detail
        let who = Conversations.name(detail)
        let resolved = detail.status == .resolved
        let replyAllowed = store.loaded && InboxRules.canReply(detail, now: now)
        let windowClosed = InboxRules.isReplyWindowClosed(detail, now: now)
        let social = InboxRules.isSocialChannel(detail.channel)
        let capabilities = InboxRules.capabilities(detail)
        return AnyView(
            VStack(spacing: 0) {
                header(who: who, resolved: resolved, server: server, session: session)
                ZStack(alignment: .bottom) {
                    if !store.loaded {
                        if store.error != nil {
                            VStack { Spacer(); Image(systemName: "icloud.slash").font(.system(size: 36)).foregroundStyle(accent.palette.muted); Spacer() }
                        } else {
                            ChatSkeleton(label: Strings.current.inbox.loading)
                        }
                    } else {
                        messages(who: who, server: server, session: session)
                    }
                    if store.hasNewMessages {
                        Button {
                            store.hasNewMessages = false
                            store.scrollRequest += 1
                        } label: {
                            HStack(spacing: 8) { Text(c.newMessages).fontWeight(.semibold); Image(systemName: "arrow.down").font(.caption) }
                                .foregroundStyle(accent.color).padding(.horizontal, 14).padding(.vertical, 10)
                                .background(accent.palette.surface, in: Capsule()).overlay(Capsule().strokeBorder(accent.palette.line, lineWidth: 1))
                        }
                        .padding(.bottom, 8)
                        .accessibilityLabel(c.latest)
                    }
                }
                if let error = store.error {
                    HStack(spacing: 4) {
                        Text(error).font(.footnote).foregroundStyle(accent.palette.danger).frame(maxWidth: .infinity, alignment: .leading)
                        Button(c.retry) { Task { await store.load(server, session, manual: true) } }.fontWeight(.semibold).foregroundStyle(accent.color).padding(8)
                        Button { store.error = nil } label: { Image(systemName: "xmark").foregroundStyle(accent.palette.muted) }.padding(6).accessibilityLabel(c.close)
                    }
                    .padding(.horizontal, 12).padding(.vertical, 6)
                    .background(accent.palette.surface)
                }
                footer(detail: detail, who: who, resolved: resolved, replyAllowed: replyAllowed, windowClosed: windowClosed, social: social, capabilities: capabilities, server: server, session: session)
            }
            .background(accent.palette.canvas)
            .toolbar(.hidden, for: .navigationBar)
            .toolbar(.hidden, for: .tabBar)
            .task {
                store.onExpired = { model.expireSession() }
                await store.start(server, session)
            }
            .onChange(of: scenePhase) { _, phase in
                store.foreground = phase == .active
                if phase == .active { now = Date(); Task { await store.load(server, session) } }
            }
            .onChange(of: Connectivity.shared.online) { _, online in
                if online { Task { await store.load(server, session, manual: true) } }
            }
            .onReceive(Timer.publish(every: 5, on: .main, in: .common).autoconnect()) { _ in now = Date() }
            .confirmationDialog(c.resolveTitle, isPresented: $confirmResolve, titleVisibility: .visible) {
                Button(c.resolveConfirm) { Task { await store.mutate(server, session) { try await PortalAPI.resolve(server, session, id: detail.id) } } }
                Button(c.cancel, role: .cancel) {}
            } message: { Text(c.resolveHint) }
            .sheet(item: $sheet) { which in
                threadSheet(which, detail: detail, who: who, resolved: resolved, capabilities: capabilities, server: server, session: session)
            }
            .sheet(item: $messageAction) { message in
                actionsSheet(message, detail: detail, who: who, server: server, session: session)
            }
            .sheet(isPresented: $templateOpen) {
                TemplatePicker(server: server, session: session, contact: TemplateContactValues(
                    contactName: (detail.contactName ?? "").isEmpty ? detail.title : detail.contactName!,
                    contactPhone: store.contactPhone(detail)?.filter(\.isNumber) ?? "",
                    contactEmail: store.contact?.email ?? detail.contactEmail ?? "",
                    agentName: session.userName
                ), externalError: store.error, onClose: { templateOpen = false }) { payload in
                    guard detail.channel == "whatsapp_cloud", capabilities.templates != false, detail.mode == .human, !resolved else { return false }
                    return await store.mutate(server, session, sent: true) { try await PortalAPI.replyWithTemplate(server, session, id: detail.id, template: payload) }
                }
                .presentationDetents([.large])
            }
        )
    }

    // MARK: Header

    private func header(who: String, resolved: Bool, server: String, session: Session) -> some View {
        let c = ChatStrings.current
        let s = Strings.current.chat
        let detail = store.detail
        return VStack(spacing: 0) {
            HStack(spacing: 2) {
                Button { dismiss() } label: { Image(systemName: "chevron.left").font(.system(size: 22, weight: .semibold)).foregroundStyle(accent.color).frame(width: 42, height: 44) }
                    .accessibilityLabel(s.back)
                Button { openDetails(server, session) } label: {
                    HStack(spacing: 10) {
                        Avatar(name: who, size: 40, radius: 14, fontSize: 18)
                        VStack(alignment: .leading, spacing: 3) {
                            Text(who).font(.headline).foregroundStyle(accent.palette.ink).lineLimit(1)
                            Text("\(Conversations.channelLabel(detail.channel)) · \(resolved ? c.resolved : detail.mode == .ai ? c.agent : detail.assigneeName ?? c.unassigned)")
                                .font(.caption).foregroundStyle(accent.palette.muted).lineLimit(1)
                        }
                        Spacer(minLength: 0)
                    }
                }
                .buttonStyle(.plain)
                .accessibilityLabel("\(c.details): \(who)")
                Button { openDetails(server, session) } label: { Image(systemName: "ellipsis").font(.system(size: 20)).foregroundStyle(accent.palette.muted).frame(width: 42, height: 44) }
                    .accessibilityLabel(c.details)
            }
            .padding(.horizontal, 6)
            HStack(spacing: 9) {
                let badgeColor = resolved ? Theme.resolvedGreen : accent.color
                HStack(spacing: 4) {
                    Image(systemName: resolved ? "checkmark.circle" : "ellipsis.bubble").font(.system(size: 12))
                    Text(resolved ? c.resolved : c.open).font(.caption.weight(.semibold))
                }
                .foregroundStyle(badgeColor).padding(.horizontal, 8).padding(.vertical, 5)
                .background(badgeColor.opacity(0.10), in: RoundedRectangle(cornerRadius: 8, style: .continuous))
                if let team = detail.teamName { Text(team).font(.caption).foregroundStyle(accent.palette.muted).lineLimit(1) }
                Spacer()
                if !resolved {
                    // Taking over lives in the footer while the assistant replies; the
                    // toolbar only offers the way back.
                    if detail.mode == .human {
                        Button(s.handBack) {
                            Task { await store.mutate(server, session) { try await PortalAPI.setMode(server, session, id: detail.id, mode: .ai) } }
                        }
                        .font(.footnote.weight(.semibold)).foregroundStyle(accent.color).disabled(store.busy || !store.loaded)
                    }
                    Button { confirmResolve = true } label: {
                        HStack(spacing: 5) {
                            Image(systemName: "checkmark.circle").font(.system(size: 15, weight: .semibold))
                            Text(c.resolveConfirm).font(.footnote.weight(.semibold))
                        }
                        .foregroundStyle(accent.onColor)
                        .padding(.horizontal, 11)
                        .frame(minHeight: 32)
                        .background(accent.color, in: Capsule())
                    }
                    .disabled(store.busy || !store.loaded).accessibilityLabel(c.resolve)
                }
            }
            .padding(.horizontal, 17)
            .padding(.vertical, 8)
        }
        .background(accent.palette.surface)
        .overlay(alignment: .bottom) { Rectangle().fill(accent.palette.line).frame(height: 0.5) }
    }

    private func openDetails(_ server: String, _ session: Session) {
        sheet = .details
        Task { await store.loadContext(server, session) }
    }

    // MARK: Messages

    private func messages(who: String, server: String, session: Session) -> some View {
        let s = Strings.current.chat
        let detail = store.detail
        return ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(spacing: 0) {
                    if detail.messages.isEmpty {
                        VStack(spacing: 12) {
                            Image(systemName: "bubble.left.and.bubble.right").font(.system(size: 34)).foregroundStyle(accent.palette.subtle)
                            Text(s.empty).foregroundStyle(accent.palette.muted).multilineTextAlignment(.center)
                        }
                        .padding(48)
                    }
                    ForEach(Array(detail.messages.enumerated()), id: \.element.id) { index, message in
                        let previous = index > 0 ? detail.messages[index - 1] : nil
                        if previous == nil || !When.sameDay(previous!.createdAt, message.createdAt) {
                            Text(When.dayLabel(message.createdAt)).font(.caption.weight(.semibold)).foregroundStyle(accent.palette.muted)
                                .padding(.horizontal, 12).padding(.vertical, 5)
                                .background(accent.palette.surface, in: RoundedRectangle(cornerRadius: 9, style: .continuous))
                                .padding(.vertical, 17)
                        }
                        MessageBubble(message: message, detail: detail, who: who, now: now, server: server, session: session, busy: store.busy) { messageAction = $0 }
                            .id(message.id)
                    }
                    Color.clear.frame(height: 1).id("bottom")
                        .onAppear { store.nearBottom = true; store.hasNewMessages = false }
                        .onDisappear { store.nearBottom = false }
                }
                .padding(.horizontal, 14)
                .padding(.top, 6)
                .padding(.bottom, 18)
            }
            .scrollDismissesKeyboard(.interactively)
            .refreshable { await store.load(server, session, manual: true) }
            .onChange(of: store.scrollRequest) { _, _ in
                withAnimation { proxy.scrollTo("bottom", anchor: .bottom) }
            }
            .onChange(of: detail.messages.last?.id) { _, _ in
                if store.nearBottom || store.initialScrollPending { proxy.scrollTo("bottom", anchor: .bottom) }
            }
            .onChange(of: store.loaded) { _, loaded in
                if loaded {
                    proxy.scrollTo("bottom", anchor: .bottom)
                    Task { try? await Task.sleep(for: .milliseconds(150)); proxy.scrollTo("bottom", anchor: .bottom); store.initialScrollPending = false }
                }
            }
        }
    }

    // MARK: Footer

    @ViewBuilder
    private func footer(detail: ConversationDetail, who: String, resolved: Bool, replyAllowed: Bool, windowClosed: Bool, social: Bool, capabilities: ChannelCapabilities, server: String, session: Session) -> some View {
        let c = ChatStrings.current
        let s = Strings.current
        VStack(spacing: 0) {
            if let quote = store.quote, replyAllowed {
                HStack {
                    Rectangle().fill(accent.color).frame(width: 3)
                    VStack(alignment: .leading, spacing: 2) {
                        Text("\(c.quoting) \(quote.senderName ?? (quote.isOutgoing ? c.agent : who))").font(.caption.weight(.bold)).foregroundStyle(accent.color)
                        Text(quote.content.isEmpty ? s.attachment.generic : quote.content).font(.caption).foregroundStyle(accent.palette.muted).lineLimit(2)
                    }
                    Spacer()
                    Button { store.quote = nil } label: { Image(systemName: "xmark").foregroundStyle(accent.palette.muted).frame(width: 42, height: 44) }.accessibilityLabel(c.cancelQuote)
                }
                .padding(.leading, 14).padding(.top, 10)
            }
            if resolved {
                HStack(spacing: 10) {
                    Image(systemName: "checkmark.circle").font(.system(size: 20)).foregroundStyle(accent.color)
                    Text(c.resolvedHint).font(.footnote).foregroundStyle(accent.palette.muted)
                }
                .padding(17)
            } else if !store.loaded {
                EmptyView()
            } else if detail.mode == .ai {
                ActionRow(label: s.chat.takeOverWide, symbol: "hand.raised", disabled: store.busy, filled: true) {
                    Task { await store.mutate(server, session) { try await PortalAPI.setMode(server, session, id: detail.id, mode: .human) } }
                }
                .padding(12)
            } else if windowClosed {
                VStack(alignment: .leading, spacing: 10) {
                    Text(social ? c.socialBlocked : c.windowClosed).fontWeight(.bold).foregroundStyle(accent.palette.ink)
                    Text(social ? socialHint(detail) : c.windowHint).font(.footnote).foregroundStyle(accent.palette.muted)
                    if !social, capabilities.templates != false {
                        ActionRow(label: c.sendTemplate, symbol: "doc.text", disabled: store.busy, filled: true) { templateOpen = true }
                    }
                }
                .padding(14)
            } else {
                if InboxRules.humanWindowOnly(detail, now: now) {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(c.socialHumanOnly).fontWeight(.bold).foregroundStyle(accent.color)
                        Text(c.socialHumanHint).font(.caption).foregroundStyle(accent.palette.muted)
                    }
                    .frame(maxWidth: .infinity, alignment: .leading).padding(12)
                }
                if detail.channel == "instagram" {
                    Text(c.socialLongText).font(.caption2).foregroundStyle(accent.palette.muted).frame(maxWidth: .infinity, alignment: .leading).padding(.horizontal, 14).padding(.top, 6)
                }
                ComposerView(
                    channel: detail.channel, capabilities: capabilities,
                    draftKey: "\(server):\(session.clientId):\(session.userId ?? "legacy"):\(detail.id)",
                    busy: store.busy,
                    onSendText: { text in await send(text, server: server, session: session) },
                    onSendFile: { file, caption in await sendFile(file, caption: caption, server: server, session: session) },
                    insertedReply: $insertedReply,
                    onSavedReplies: { sheet = .canned; Task { await store.loadCanned(server, session) } },
                    onAttachmentSelected: { store.quote = nil },
                    onError: { store.error = $0 }
                )
            }
        }
        .background(accent.palette.surface)
        .overlay(alignment: .top) { Rectangle().fill(accent.palette.line).frame(height: 0.5) }
    }

    private func socialHint(_ detail: ConversationDetail) -> String {
        let c = ChatStrings.current
        switch detail.replyBlockReason {
        case "channel_disconnected": return c.socialDisconnected
        case "authorization_expired": return c.socialAuthorization
        case "another_app_controls_conversation": return c.socialControl
        default: return c.socialWindowHint
        }
    }

    private func send(_ text: String, server: String, session: Session) async -> Bool {
        let detail = store.detail
        guard InboxRules.canReply(detail), InboxRules.capabilities(detail).text == true, !text.trimmingCharacters(in: .whitespaces).isEmpty else { return false }
        let quoted = store.quote.flatMap { InboxRules.canQuote(detail, $0) ? $0.id : nil }
        let ok = await store.mutate(server, session, sent: true) { try await PortalAPI.reply(server, session, id: detail.id, content: text, quotedMessageId: quoted) }
        if ok { store.quote = nil }
        return ok
    }

    private func sendFile(_ file: OutgoingFile, caption: String, server: String, session: Session) async -> Bool {
        let detail = store.detail
        let capabilities = InboxRules.capabilities(detail)
        guard InboxRules.canReply(detail), InboxRules.acceptsAttachment(channel: detail.channel, capabilities: capabilities, mime: file.mime),
              caption.trimmingCharacters(in: .whitespaces).isEmpty || capabilities.text == true else { return false }
        let ok = await store.mutate(server, session, sent: true) { try await PortalAPI.replyWithFile(server, session, id: detail.id, file: file, caption: caption) }
        if ok { store.quote = nil }
        return ok
    }

    // MARK: Sheets

    private func sheetTitle(_ which: Sheet) -> String {
        let c = ChatStrings.current
        switch which {
        case .assignee: return c.assignee
        case .team: return c.team
        case .media: return c.shared
        case .canned: return c.canned
        case .details: return c.details
        }
    }

    @ViewBuilder
    private func threadSheet(_ which: Sheet, detail: ConversationDetail, who: String, resolved: Bool, capabilities: ChannelCapabilities, server: String, session: Session) -> some View {
        let c = ChatStrings.current
        let s = Strings.current
        SheetScaffold(title: sheetTitle(which), closeDisabled: store.busy, onClose: { sheet = nil }) {
            if store.contextLoading, which != .media { ProgressView().tint(accent.color).frame(maxWidth: .infinity).padding(16) }
            switch which {
            case .details:
                VStack(spacing: 9) {
                    Avatar(name: who, size: 70, radius: 24, fontSize: 26)
                    Text(who).font(.title3.weight(.bold)).foregroundStyle(accent.palette.ink).multilineTextAlignment(.center)
                    Text("\(Conversations.channelLabel(detail.channel)) · \(resolved ? c.resolved : c.open)").foregroundStyle(accent.palette.muted)
                }
                .frame(maxWidth: .infinity).padding(.bottom, 16)
                ActionRow(label: c.assignee, subtitle: detail.assigneeName ?? (detail.mode == .ai ? c.agent : c.unassigned), symbol: "person", disabled: resolved || store.busy || store.contextLoading) { sheet = .assignee }
                ActionRow(label: c.team, subtitle: detail.teamName ?? c.noTeam, symbol: "person.2", disabled: resolved || store.busy || store.contextLoading) { sheet = .team }
                ActionRow(label: c.shared, symbol: "photo.on.rectangle") { sheet = .media }
                if detail.channel == "whatsapp_cloud", capabilities.templates != false, detail.mode == .human, !resolved {
                    ActionRow(label: c.sendTemplate, symbol: "doc.text", disabled: store.busy) {
                        sheet = nil
                        Task { try? await Task.sleep(for: .milliseconds(350)); templateOpen = true }
                    }
                }
                if let contact = store.contact {
                    contactEditor(contact, detail: detail, server: server, session: session)
                } else if let phone = store.contactPhone(detail) {
                    Text("\(c.phone): \(DialCodes.format(phone))").foregroundStyle(accent.palette.muted).padding(12)
                }
            case .assignee:
                ForEach(store.members) { member in
                    ActionRow(label: "\(member.name.isEmpty ? member.email : member.name)\(member.id == session.userId ? " (\(c.me))" : "")", subtitle: member.email, selected: detail.assigneeId == member.id, disabled: store.busy) {
                        Task { if await store.mutate(server, session, { try await PortalAPI.assign(server, session, id: detail.id, assigneeId: member.id) }) { sheet = .details } }
                    }
                }
            case .team:
                ActionRow(label: c.noTeam, selected: detail.teamId == nil, disabled: store.busy) {
                    Task { if await store.mutate(server, session, { try await PortalAPI.setTeam(server, session, id: detail.id, teamId: nil) }) { sheet = .details } }
                }
                ForEach(store.teams) { team in
                    ActionRow(label: team.name, subtitle: team.description.isEmpty ? nil : team.description, selected: detail.teamId == team.id, disabled: store.busy) {
                        Task { if await store.mutate(server, session, { try await PortalAPI.setTeam(server, session, id: detail.id, teamId: team.id) }) { sheet = .details } }
                    }
                }
            case .media:
                let withFiles = detail.messages.filter { !$0.attachments.isEmpty }
                if withFiles.isEmpty {
                    Text(c.noMedia).foregroundStyle(accent.palette.muted).padding(16)
                } else {
                    ForEach(withFiles) { message in
                        ForEach(message.attachments) { attachment in
                            VStack(alignment: .leading, spacing: 9) {
                                AttachmentView(attachment: attachment, server: server, session: session, conversationId: detail.id, outgoing: false)
                                Text("\(When.shortDate(message.createdAt)) · \(When.time(message.createdAt))").font(.caption2).foregroundStyle(accent.palette.muted)
                            }
                            .padding(14)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .background(accent.palette.raised, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
                            .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous).strokeBorder(accent.palette.line, lineWidth: 0.5))
                        }
                    }
                }
            case .canned:
                FormTextField(text: Binding(get: { store.cannedQuery }, set: { store.cannedQuery = $0 }), placeholder: c.searchReplies)
                let query = store.cannedQuery.lowercased()
                ForEach(store.canned.filter { query.isEmpty || "\($0.shortcut) \($0.content)".lowercased().contains(query) }) { item in
                    ActionRow(label: "/\(item.shortcut)", subtitle: item.content) {
                        insertedReply = InboxRules.interpolate(item.content, InboxRules.CannedVariables(
                            contactName: (detail.contactName ?? "").isEmpty ? detail.title : detail.contactName!,
                            contactPhone: store.contactPhone(detail) ?? "",
                            contactEmail: store.contact?.email ?? detail.contactEmail ?? "",
                            agentName: session.userName
                        ))
                        sheet = nil
                    }
                }
                if !store.contextLoading, store.canned.isEmpty { Text(c.noCanned).foregroundStyle(accent.palette.muted).padding(12) }
            }
            if let contextError = store.contextError, which != .media {
                Text(contextError).foregroundStyle(accent.palette.danger).padding(.vertical, 10)
                ActionRow(label: c.retry) { Task { if which == .canned { await store.loadCanned(server, session) } else { await store.loadContext(server, session) } } }
            }
            if let error = store.error, !store.busy, which == .team || which == .assignee {
                Text(error).foregroundStyle(accent.palette.danger).padding(10)
            }
            let _ = s
        }
        .presentationDetents([.large])
    }

    @ViewBuilder
    private func contactEditor(_ contact: Contact, detail: ConversationDetail, server: String, session: Session) -> some View {
        let c = ChatStrings.current
        let dirty = store.contactName != contact.name || store.contactEmail != (contact.email ?? "") || store.contactNotes != contact.notes
        VStack(alignment: .leading, spacing: 10) {
            SectionTitle(text: c.contact)
            Text("\(c.phone): \(store.contactPhone(detail).map { DialCodes.format($0) } ?? "–")").foregroundStyle(accent.palette.muted)
            Text(c.name).font(.caption.weight(.semibold)).foregroundStyle(accent.palette.muted)
            FormTextField(text: Binding(get: { store.contactName }, set: { store.contactName = $0 }), disabled: store.busy, accessibilityLabel: c.name)
            Text(c.email).font(.caption.weight(.semibold)).foregroundStyle(accent.palette.muted)
            FormTextField(text: Binding(get: { store.contactEmail }, set: { store.contactEmail = $0 }), keyboard: .emailAddress, disabled: store.busy, autocapitalize: .never, accessibilityLabel: c.email)
            Text(c.notes).font(.caption.weight(.semibold)).foregroundStyle(accent.palette.muted)
            FormTextField(text: Binding(get: { store.contactNotes }, set: { store.contactNotes = $0 }), multiline: true, disabled: store.busy, accessibilityLabel: c.notes)
            Text(c.notesHint).font(.caption).foregroundStyle(accent.palette.muted)
            if dirty { ActionRow(label: c.save, disabled: store.busy, filled: true) { Task { await store.saveContact(server, session) } } }
            SectionTitle(text: c.history)
            if store.history.isEmpty {
                Text(c.noHistory).font(.footnote).foregroundStyle(accent.palette.muted)
            } else {
                ForEach(store.history) { item in
                    let preview = item.preview.isEmpty ? "" : " · \(String(item.preview.prefix(90)))"
                    ActionRow(label: item.title.isEmpty ? Conversations.name(detail) : item.title,
                              subtitle: "\(item.status == .resolved ? c.resolved : c.open) · \(When.shortDate(item.createdAt))\(preview)",
                              symbol: item.status == .resolved ? "checkmark.circle" : "bubble.left") {
                        sheet = nil
                        model.openConversation(item)
                    }
                }
            }
        }
        .padding(.top, 14)
    }

    private func actionsSheet(_ message: Message, detail: ConversationDetail, who: String, server: String, session: Session) -> some View {
        let c = ChatStrings.current
        let s = Strings.current
        return SheetScaffold(title: c.actions, onClose: { messageAction = nil }) {
            Text(message.content.isEmpty ? s.attachment.generic : message.content).foregroundStyle(accent.palette.muted).lineLimit(4).padding(8)
            if InboxRules.canQuote(detail, message, now: now) {
                ActionRow(label: c.quote, symbol: "arrowshape.turn.up.left") { store.quote = message; messageAction = nil }
            }
            if InboxRules.canReact(detail, message) {
                SectionTitle(text: c.react)
                HStack(spacing: 6) {
                    ForEach(["👍", "❤️", "😂", "😮", "😢", "🙏"], id: \.self) { emoji in
                        Button {
                            messageAction = nil
                            Task { await store.mutate(server, session) { try await PortalAPI.react(server, session, id: detail.id, messageId: message.id, emoji: emoji) } }
                        } label: {
                            Text(emoji).font(.system(size: 25)).padding(10)
                                .background(message.reaction == emoji ? accent.tint() : accent.palette.canvas, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                        }
                        .disabled(store.busy)
                        .accessibilityLabel("\(c.react) \(emoji)")
                    }
                }
                .padding(.vertical, 10)
                if message.reaction != nil {
                    ActionRow(label: c.removeReaction) {
                        messageAction = nil
                        Task { await store.mutate(server, session) { try await PortalAPI.react(server, session, id: detail.id, messageId: message.id, emoji: "") } }
                    }
                }
            }
        }
        .presentationDetents([.medium, .large])
    }
}

/// One message, drawn as a bubble or an activity line.
struct MessageBubble: View {
    let message: Message
    let detail: ConversationDetail
    let who: String
    let now: Date
    let server: String
    let session: Session
    let busy: Bool
    let onAction: (Message) -> Void
    @Environment(\.accent) private var accent
    @Environment(\.colorScheme) private var scheme

    var body: some View {
        let c = ChatStrings.current
        let s = Strings.current
        if message.isActivity {
            Text("\(c.activityLabel(message)) · \(When.time(message.createdAt))")
                .font(.caption).foregroundStyle(accent.palette.muted).multilineTextAlignment(.center)
                .padding(.vertical, 10).padding(.horizontal, 16)
                .frame(maxWidth: .infinity)
        } else {
            let outgoing = message.isOutgoing
            let ai = message.isAI
            let bubble: Color = outgoing && !ai ? accent.color : ai ? accent.tint(scheme == .dark ? 0.23 : 0.12) : accent.palette.bubbleIn
            let text: Color = outgoing && !ai ? accent.onColor : accent.palette.ink
            let actionable = InboxRules.canQuote(detail, message, now: now) || InboxRules.canReact(detail, message)
            let quoted = message.quotedMessageId.flatMap { id in detail.messages.first { $0.id == id } }
            let delivery = InboxRules.delivery(message.deliveryStatus)
            HStack {
                if outgoing { Spacer(minLength: 40) }
                VStack(alignment: .leading, spacing: 5) {
                    HStack(spacing: 15) {
                        Text("\(message.senderName ?? (outgoing ? c.agent : who))\(ai ? " · \(c.ai)" : "")")
                            .font(.caption2.weight(.bold)).foregroundStyle(text.opacity(0.8))
                        Spacer(minLength: 0)
                        if actionable {
                            Button { onAction(message) } label: { Image(systemName: "ellipsis").font(.system(size: 15)).foregroundStyle(text) }
                                .disabled(busy).accessibilityLabel(c.actions)
                        }
                    }
                    if message.quotedMessageId != nil {
                        VStack(alignment: .leading, spacing: 3) {
                            Text(quoted?.senderName ?? (quoted?.isOutgoing == true ? c.agent : who)).font(.caption2.weight(.bold)).foregroundStyle(text).lineLimit(1)
                            Text(quoted.map { $0.content.isEmpty ? ($0.attachments.isEmpty ? c.unavailableQuote : s.attachment.generic) : $0.content } ?? c.unavailableQuote)
                                .font(.caption).foregroundStyle(text).lineLimit(3)
                        }
                        .padding(8)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(Color.gray.opacity(0.12), in: RoundedRectangle(cornerRadius: 5))
                        .overlay(alignment: .leading) { Rectangle().fill(text).frame(width: 3) }
                        .clipShape(RoundedRectangle(cornerRadius: 5))
                    }
                    ForEach(message.attachments) { attachment in
                        AttachmentView(attachment: attachment, server: server, session: session, conversationId: detail.id, outgoing: outgoing && !ai)
                            .padding(.vertical, 4)
                    }
                    if !message.content.isEmpty {
                        Text(RichText.attributed(message.content)).font(.subheadline).foregroundStyle(text).textSelection(.enabled)
                    }
                    HStack(spacing: 5) {
                        Spacer(minLength: 0)
                        Text(When.time(message.createdAt)).font(.system(size: 10)).foregroundStyle(text.opacity(0.7))
                        if outgoing, detail.channel == "whatsapp_cloud" || InboxRules.isSocialChannel(detail.channel), let delivery {
                            Image(systemName: delivery.symbol).font(.system(size: 11)).foregroundStyle(text)
                            Text(c.delivery(delivery.label)).font(.system(size: 10)).foregroundStyle(text.opacity(0.8))
                        }
                    }
                    if let error = message.deliveryError, !error.isEmpty { Text(error).font(.caption2).foregroundStyle(text) }
                    if message.reaction != nil || message.incomingReaction != nil {
                        HStack(spacing: 5) {
                            ForEach([message.reaction, message.incomingReaction].compactMap { $0 }.filter { !$0.isEmpty }, id: \.self) { reaction in
                                Text(reaction).font(.subheadline).padding(.horizontal, 7).padding(.vertical, 2).background(accent.palette.surface, in: Capsule())
                            }
                        }
                    }
                }
                .padding(.horizontal, 12).padding(.top, 9).padding(.bottom, 6)
                .frame(minWidth: 94, alignment: .leading)
                .background(bubble, in: UnevenRoundedRectangle(cornerRadii: .init(topLeading: 18, bottomLeading: outgoing ? 18 : 5, bottomTrailing: outgoing ? 5 : 18, topTrailing: 18), style: .continuous))
                .frame(maxWidth: 320, alignment: outgoing ? .trailing : .leading)
                .contextMenu {
                    if actionable, !busy { Button(c.actions) { onAction(message) } }
                }
                if !outgoing { Spacer(minLength: 40) }
            }
            .padding(.vertical, 4)
        }
    }
}

/// Loads, polls and mutates one conversation.
@MainActor
@Observable
final class ChatStore {
    var detail: ConversationDetail
    var loaded = false
    var busy = false
    var error: String?
    var quote: Message?
    var hasNewMessages = false
    var nearBottom = true
    var initialScrollPending = true
    var scrollRequest = 0
    var foreground = true
    var members: [PortalMember] = []
    var teams: [Team] = []
    var contact: Contact?
    var contactName = ""
    var contactEmail = ""
    var contactNotes = ""
    var history: [Conversation] = []
    var canned: [CannedReply] = []
    var cannedQuery = ""
    var contextLoading = false
    var contextError: String?
    var onExpired: (() -> Void)?

    private var errorSource: String?
    private var loading = false
    private var mutating = false
    private var revision = 0
    private var lastMessageId: String?
    private var readSignature: String?

    init(conversation: Conversation) {
        detail = ConversationDetail(opening: conversation)
    }

    func contactPhone(_ detail: ConversationDetail) -> String? {
        contact?.phone ?? (InboxRules.isWhatsApp(detail.channel) ? Conversations.phone(from: detail.externalChatId) : nil)
    }

    private func report(_ error: Error, source: String = "action") {
        if let failure = error as? APIError, failure.isUnauthorized { onExpired?() }
        errorSource = source
        self.error = (error as? APIError)?.message ?? ChatStrings.current.updateFailed
    }

    private func apply(_ next: ConversationDetail) {
        let nextId = next.messages.last?.id
        if let lastMessageId, nextId != lastMessageId, !nearBottom { hasNewMessages = true }
        lastMessageId = nextId
        detail = next
        let snapshot = next
        Task.detached(priority: .utility) { ThreadCache.save(snapshot) }
    }

    func start(_ server: String, _ session: Session) async {
        // The cached copy opens the thread at once; the server's answer replaces it.
        if !loaded, let cached = ThreadCache.load(detail.id) {
            detail = cached
            lastMessageId = cached.messages.last?.id
            loaded = true
        }
        await load(server, session)
        while !Task.isCancelled {
            try? await Task.sleep(for: .seconds(5))
            guard !Task.isCancelled else { return }
            if foreground { await load(server, session) }
        }
    }

    func load(_ server: String, _ session: Session, manual: Bool = false) async {
        guard !loading, !mutating, foreground || manual else { return }
        loading = true
        let generation = revision
        defer { loading = false }
        do {
            let next = try await PortalAPI.conversation(server, session, id: detail.id)
            guard generation == revision else { return }
            apply(next)
            loaded = true
            if manual || errorSource == "load" { error = nil; errorSource = nil }
            // Reading activity alone must not generate another write every poll.
            let signature = "\(next.id):\(next.lastInboundAt ?? next.createdAt)"
            if readSignature != signature {
                try await PortalAPI.markRead(server, session, id: next.id)
                readSignature = signature
            }
        } catch is CancellationError {
        } catch { report(error, source: "load") }
    }

    func mutate(_ server: String, _ session: Session, sent: Bool = false, _ action: @escaping () async throws -> ConversationDetail) async -> Bool {
        guard !mutating else { return false }
        mutating = true
        revision += 1
        busy = true
        error = nil
        defer { mutating = false; busy = false }
        do {
            let next = try await action()
            if sent { nearBottom = true; hasNewMessages = false; scrollRequest += 1 }
            apply(next)
            return true
        } catch {
            report(error)
            return false
        }
    }

    func loadContext(_ server: String, _ session: Session) async {
        contextLoading = true
        contextError = nil
        defer { contextLoading = false }
        var failure: Error?
        do { members = try await PortalAPI.members(server, session) } catch { failure = error }
        do { teams = try await PortalAPI.teams(server, session) } catch { failure = error }
        if let contactId = detail.contactId {
            do {
                let data = try await PortalAPI.contact(server, session, id: contactId)
                contact = data
                contactName = data.name
                contactEmail = data.email ?? ""
                contactNotes = data.notes
            } catch { failure = error }
            do { history = try await PortalAPI.contactConversations(server, session, id: contactId).filter { $0.id != detail.id } } catch { failure = error }
        }
        if let failure {
            if let api = failure as? APIError, api.isUnauthorized { onExpired?() }
            contextError = (failure as? APIError)?.message ?? ChatStrings.current.loadFailed
        }
    }

    func loadCanned(_ server: String, _ session: Session) async {
        cannedQuery = ""
        contextLoading = true
        contextError = nil
        defer { contextLoading = false }
        do { canned = try await PortalAPI.cannedReplies(server, session) }
        catch { contextError = (error as? APIError)?.message ?? ChatStrings.current.loadFailed }
    }

    func saveContact(_ server: String, _ session: Session) async {
        guard let contact, !mutating else { return }
        mutating = true
        busy = true
        contextError = nil
        defer { mutating = false; busy = false }
        do {
            let saved = try await PortalAPI.updateContact(server, session, id: contact.id, ContactUpdate(
                name: contactName.trimmingCharacters(in: .whitespaces),
                email: .some(contactEmail.trimmingCharacters(in: .whitespaces).isEmpty ? nil : contactEmail.trimmingCharacters(in: .whitespaces)),
                notes: contactNotes
            ))
            self.contact = saved
            contactName = saved.name
            contactEmail = saved.email ?? ""
            contactNotes = saved.notes
        } catch {
            contextError = (error as? APIError)?.message ?? ChatStrings.current.updateFailed
        }
    }
}
