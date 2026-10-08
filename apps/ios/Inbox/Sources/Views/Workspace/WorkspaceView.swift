import Charts
import SwiftUI

/// Teams, people and your own availability.
struct TeamView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.accent) private var accent

    var body: some View {
        let s = WorkspaceStrings.current
        guard let session = model.session else { return AnyView(EmptyView()) }
        return AnyView(
            VStack(spacing: 0) {
                VStack(alignment: .leading, spacing: 4) {
                    Text(s.teams).font(.system(size: 28, weight: .bold)).foregroundStyle(accent.palette.ink)
                    Text(s.subtitle).font(.caption).foregroundStyle(accent.palette.muted)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(18)
                TeamsPanel(server: model.server, session: session)
            }
            .background(accent.palette.surface)
            .toolbar(.hidden, for: .navigationBar)
        )
    }
}

/// Operational reports, for the people whose role may see them.
struct ReportsView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.accent) private var accent

    var body: some View {
        let s = WorkspaceStrings.current
        guard let session = model.session, session.has("reports.view") else { return AnyView(EmptyView()) }
        return AnyView(
            VStack(spacing: 0) {
                VStack(alignment: .leading, spacing: 4) {
                    Text(s.reports).font(.system(size: 28, weight: .bold)).foregroundStyle(accent.palette.ink)
                    Text(s.reportsSubtitle).font(.caption).foregroundStyle(accent.palette.muted)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(18)
                ReportsPanel(server: model.server, session: session)
            }
            .background(accent.palette.surface)
            .toolbar(.hidden, for: .navigationBar)
        )
    }
}

struct TeamsPanel: View {
    let server: String
    let session: Session
    @Environment(AppModel.self) private var model
    @Environment(\.accent) private var accent
    @State private var teams: [Team] = []
    @State private var members: [PortalMember] = []
    @State private var loading = true
    @State private var error: String?
    @State private var editing: Team?
    @State private var creating = false
    @State private var saving = false
    @State private var saveError: String?
    @State private var availabilityBusy = false
    @State private var reload = 0

    private var canManage: Bool { session.has("teams.manage") }

    var body: some View {
        let s = WorkspaceStrings.current
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                if let error { ErrorNotice(message: error, retryLabel: s.retry, retry: { reload += 1 }) }
                HStack {
                    Text(s.teams).font(.title3.weight(.semibold)).foregroundStyle(accent.palette.ink)
                    Spacer()
                    if canManage {
                        Button { saveError = nil; creating = true } label: {
                            HStack(spacing: 6) { Image(systemName: "plus"); Text(s.newTeam) }.font(.subheadline).foregroundStyle(accent.color)
                                .padding(11).background(accent.tint(), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                        }
                    }
                }
                if loading {
                    ProgressView().tint(accent.color).frame(maxWidth: .infinity).padding(30)
                } else if teams.isEmpty {
                    Card {
                        Image(systemName: "person.2").font(.system(size: 32)).foregroundStyle(accent.palette.subtle)
                        Text(s.noTeams).font(.body.weight(.semibold)).foregroundStyle(accent.palette.ink)
                        Text(canManage ? s.noTeamsHint : s.noTeamsReadOnlyHint).font(.subheadline).foregroundStyle(accent.palette.muted)
                    }
                } else {
                    ForEach(teams) { team in
                        Button { if canManage { saveError = nil; editing = team } } label: {
                            Card {
                                HStack(spacing: 10) {
                                    Text(team.name).font(.body.weight(.semibold)).foregroundStyle(accent.palette.ink)
                                    Spacer()
                                    if team.isDefault {
                                        Text(s.defaultTeam).font(.system(size: 10)).foregroundStyle(accent.color).padding(.horizontal, 7).padding(.vertical, 4).background(accent.tint(), in: RoundedRectangle(cornerRadius: 6))
                                    }
                                    if canManage { Image(systemName: "square.and.pencil").foregroundStyle(accent.color) }
                                }
                                if !team.description.isEmpty { Text(team.description).font(.subheadline).foregroundStyle(accent.palette.muted) }
                                Text("\(team.strategy == "least_busy" ? s.leastBusy : s.roundRobin) · \(team.openCount) \(s.open)\(team.unassignedCount > 0 ? " · \(team.unassignedCount) \(s.unassigned)" : "")")
                                    .font(.caption).foregroundStyle(accent.palette.muted)
                                if team.members.isEmpty {
                                    Text(s.noMembers).foregroundStyle(accent.palette.muted)
                                } else {
                                    FlowLayout(spacing: 8) {
                                        ForEach(team.members) { member in
                                            HStack(spacing: 6) {
                                                Circle().fill(member.availability == .online ? Theme.onlineGreen : accent.palette.subtle).frame(width: 7, height: 7)
                                                Text(member.name.isEmpty ? member.email : member.name).font(.caption).foregroundStyle(accent.palette.ink)
                                            }
                                            .padding(.horizontal, 8).padding(.vertical, 6)
                                            .background(accent.palette.canvas, in: RoundedRectangle(cornerRadius: 8))
                                        }
                                    }
                                }
                            }
                        }
                        .buttonStyle(.plain)
                        .disabled(!canManage)
                        .accessibilityLabel(canManage ? "\(s.editTeam): \(team.name)" : team.name)
                    }
                }
                Text(s.people).font(.title3.weight(.semibold)).foregroundStyle(accent.palette.ink).padding(.top, 22)
                ForEach(members) { member in
                    HStack(spacing: 12) {
                        Circle().fill(member.availability == .online ? Theme.onlineGreen : accent.palette.subtle).frame(width: 7, height: 7)
                        VStack(alignment: .leading, spacing: 4) {
                            Text("\(member.name.isEmpty ? member.email : member.name)\(member.id == session.userId ? " · \(s.me)" : "")").font(.body.weight(.semibold)).foregroundStyle(accent.palette.ink)
                            Text(member.availability == .online ? s.online : s.away).font(.caption).foregroundStyle(accent.palette.muted)
                        }
                        Spacer()
                        if member.id == session.userId {
                            Button { Task { await toggleAvailability(member) } } label: {
                                if availabilityBusy { ProgressView().tint(accent.color) }
                                else { Text(member.availability == .online ? s.goAway : s.goOnline).font(.caption).foregroundStyle(accent.color) }
                            }
                            .disabled(availabilityBusy)
                            .frame(minHeight: 44)
                            .accessibilityLabel(s.changeAvailability)
                        }
                    }
                    .padding(.vertical, 10)
                    .overlay(alignment: .bottom) { Rectangle().fill(accent.palette.line).frame(height: 0.5) }
                }
            }
            .padding(20)
        }
        .refreshable { await load() }
        .task(id: reload) { await load() }
        .sheet(isPresented: $creating) { editorSheet(team: nil) }
        .sheet(item: $editing) { team in editorSheet(team: team) }
    }

    private func editorSheet(team: Team?) -> some View {
        let s = WorkspaceStrings.current
        return NavigationStack {
            VStack(spacing: 0) {
                if let saveError { Text(saveError).foregroundStyle(accent.palette.danger).padding(.horizontal, 20).padding(.top, 16) }
                TeamEditor(team: team, members: members, saving: saving) { payload in Task { await save(payload, team: team) } }
            }
            .background(accent.palette.surface)
            .navigationTitle(team == nil ? s.newTeam : s.editTeam)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .topBarLeading) { Button(s.cancel) { creating = false; editing = nil }.disabled(saving) } }
        }
        .tint(accent.color)
        .interactiveDismissDisabled(saving)
    }

    private func handle(_ error: Error) -> String {
        if let api = error as? APIError {
            if api.isUnauthorized { model.expireSession() }
            return api.message
        }
        return WorkspaceStrings.current.loadFailed
    }

    private func load() async {
        do {
            async let groups = PortalAPI.teams(server, session)
            async let people = PortalAPI.members(server, session)
            let (nextTeams, nextMembers) = try await (groups, people)
            teams = nextTeams
            members = nextMembers
            error = nil
        } catch is CancellationError {
        } catch { self.error = handle(error) }
        loading = false
    }

    private func save(_ payload: TeamUpdate, team: Team?) async {
        guard canManage, !saving else { return }
        saving = true
        saveError = nil
        defer { saving = false }
        do {
            if let team { _ = try await PortalAPI.updateTeam(server, session, id: team.id, payload) }
            else { _ = try await PortalAPI.createTeam(server, session, payload) }
            creating = false
            editing = nil
            await load()
        } catch {
            if let api = error as? APIError, api.status == 409 { saveError = WorkspaceStrings.current.duplicateName }
            else { saveError = handle(error) }
        }
    }

    private func toggleAvailability(_ member: PortalMember) async {
        guard !availabilityBusy else { return }
        availabilityBusy = true
        defer { availabilityBusy = false }
        do {
            let updated = try await PortalAPI.setAvailability(server, session, member.availability == .online ? .away : .online)
            members = members.map { $0.id == updated.id ? updated : $0 }
            teams = teams.map { team in
                var copy = team
                copy.members = team.members.map { $0.id == updated.id ? updated : $0 }
                return copy
            }
            error = nil
        } catch { self.error = handle(error) }
    }
}

struct TeamEditor: View {
    let team: Team?
    let members: [PortalMember]
    let saving: Bool
    let onSave: (TeamUpdate) -> Void
    @Environment(\.accent) private var accent
    @State private var name: String
    @State private var description: String
    @State private var strategy: String
    @State private var channels: [String]
    @State private var memberIds: [String]
    @State private var isDefault: Bool

    static let channels = ["whatsapp", "whatsapp_cloud", "instagram", "messenger", "widget"]

    init(team: Team?, members: [PortalMember], saving: Bool, onSave: @escaping (TeamUpdate) -> Void) {
        self.team = team
        self.members = members
        self.saving = saving
        self.onSave = onSave
        _name = State(initialValue: team?.name ?? "")
        _description = State(initialValue: team?.description ?? "")
        _strategy = State(initialValue: team?.strategy ?? "round_robin")
        _channels = State(initialValue: team?.channels ?? [])
        _memberIds = State(initialValue: team?.members.map(\.id) ?? [])
        _isDefault = State(initialValue: team?.isDefault ?? false)
    }

    private func toggle(_ rows: inout [String], _ value: String) {
        if let index = rows.firstIndex(of: value) { rows.remove(at: index) } else { rows.append(value) }
    }

    var body: some View {
        let s = WorkspaceStrings.current
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                FieldLabel(text: s.teamName)
                FormTextField(text: $name, disabled: saving, accessibilityLabel: s.teamName)
                FieldLabel(text: s.description)
                FormTextField(text: $description, multiline: true, disabled: saving, accessibilityLabel: s.description)
                FieldLabel(text: s.strategy)
                ChoiceRow(label: s.roundRobin, subtitle: s.roundRobinHint, selected: strategy == "round_robin", disabled: saving) { strategy = "round_robin" }
                ChoiceRow(label: s.leastBusy, subtitle: s.leastBusyHint, selected: strategy == "least_busy", disabled: saving) { strategy = "least_busy" }
                FieldLabel(text: s.members)
                if members.isEmpty { Text(s.noMembers).foregroundStyle(accent.palette.muted) }
                ForEach(members) { member in
                    ChoiceRow(label: member.name.isEmpty ? member.email : member.name, subtitle: member.availability == .online ? s.online : s.away,
                              selected: memberIds.contains(member.id), checkbox: true, disabled: saving) { toggle(&memberIds, member.id) }
                }
                FieldLabel(text: s.channels)
                Text(s.channelHint).font(.caption).foregroundStyle(accent.palette.muted)
                ForEach(TeamEditor.channels, id: \.self) { channel in
                    Toggle(isOn: Binding(get: { channels.contains(channel) }, set: { _ in toggle(&channels, channel) })) {
                        Text(Conversations.channelName(channel)).foregroundStyle(accent.palette.ink)
                    }
                    .tint(accent.color)
                    .disabled(saving)
                    .padding(.vertical, 4)
                }
                Toggle(isOn: $isDefault) {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(s.defaultTeam).font(.body.weight(.semibold)).foregroundStyle(accent.palette.ink)
                        Text(s.defaultHint).font(.caption).foregroundStyle(accent.palette.muted)
                    }
                }
                .tint(accent.color)
                .disabled(saving)
                .padding(.top, 12)
                PrimaryButton(label: s.save, busy: saving, disabled: name.trimmingCharacters(in: .whitespaces).isEmpty) {
                    onSave(TeamUpdate(name: name.trimmingCharacters(in: .whitespaces), description: description.trimmingCharacters(in: .whitespacesAndNewlines), strategy: strategy, channels: channels, isDefault: isDefault, memberIds: memberIds))
                }
                .padding(.top, 16)
            }
            .padding(20)
        }
        .scrollDismissesKeyboard(.interactively)
    }
}

struct ReportsPanel: View {
    let server: String
    let session: Session
    @Environment(AppModel.self) private var model
    @Environment(\.accent) private var accent
    @State private var days = 7
    @State private var fromDate = Calendar.current.date(byAdding: .day, value: -29, to: Date()) ?? Date()
    @State private var toDate = Date()
    @State private var channel = ""
    @State private var team = ""
    @State private var teams: [Team] = []
    @State private var report: PortalReport?
    @State private var loading = true
    @State private var error: String?
    @State private var reload = 0
    @State private var selectedDay: Date?

    var body: some View {
        let s = WorkspaceStrings.current
        let range = days == 0 ? Reports.range(from: fromDate, to: toDate) : Reports.range(days: days)
        let span = Reports.spanDays(range)
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                Picker("", selection: $days) {
                    Text(s.days7).tag(7)
                    Text(s.days30).tag(30)
                    Text(s.days90).tag(90)
                    Text(s.custom).tag(0)
                }
                .pickerStyle(.segmented)
                if days == 0 {
                    HStack(spacing: 10) {
                        DatePicker(s.from, selection: $fromDate, in: ...Date(), displayedComponents: .date).labelsHidden()
                        Text("–").foregroundStyle(accent.palette.muted)
                        DatePicker(s.to, selection: $toDate, in: fromDate...Date(), displayedComponents: .date).labelsHidden()
                        Spacer(minLength: 0)
                    }
                    .tint(accent.color)
                }
                HStack(spacing: 10) {
                    filterMenu(label: channel.isEmpty ? s.allChannels : Conversations.channelName(channel), symbol: "bubble.left.and.bubble.right", active: !channel.isEmpty) {
                        Button(s.allChannels) { channel = "" }
                        ForEach(TeamEditor.channels, id: \.self) { value in Button(Conversations.channelName(value)) { channel = value } }
                    }
                    if !teams.isEmpty {
                        filterMenu(label: team.isEmpty ? s.allTeams : (teams.first { $0.id == team }?.name ?? s.allTeams), symbol: "person.3", active: !team.isEmpty) {
                            Button(s.allTeams) { team = "" }
                            ForEach(teams) { row in Button(row.name) { team = row.id } }
                        }
                    }
                }
                Text("\(Reports.dayLabel(range.from)) – \(Reports.dayLabel(range.to)) · \(Reports.utcLabel(tzOffset: range.tzOffset))").font(.caption).foregroundStyle(accent.palette.muted)
                if let error { ErrorNotice(message: error, retryLabel: s.retry, retry: { reload += 1 }) }
                if loading {
                    ProgressView().tint(accent.color).frame(maxWidth: .infinity).padding(30)
                } else if let report {
                    let metrics: [(String, String)] = [
                        (s.started, String(report.started)), (s.resolved, String(report.resolved)), (s.openNow, String(report.openNow)), (s.agentsOnline, String(report.agentsOnline)),
                        (s.inbound, String(report.inboundMessages)), (s.humanReplies, String(report.humanReplies)), (s.aiReplies, String(report.aiReplies)), (s.activeContacts, String(report.activeContacts)),
                        (s.firstReply, Reports.duration(report.avgFirstReplySeconds, s)), (s.resolutionTime, Reports.duration(report.avgResolutionSeconds, s)),
                    ]
                    LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 10) {
                        ForEach(metrics, id: \.0) { label, value in
                            VStack(alignment: .leading, spacing: 6) {
                                Text(value).font(.title2.weight(.bold)).foregroundStyle(accent.palette.ink)
                                Text(label).font(.caption).foregroundStyle(accent.palette.muted)
                            }
                            .padding(16)
                            .frame(maxWidth: .infinity, minHeight: 94, alignment: .topLeading)
                            .background(accent.palette.raised, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
                            .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).strokeBorder(accent.palette.line, lineWidth: 0.5))
                        }
                    }
                    .padding(.top, 8)
                    Text(s.currentHint).font(.caption).foregroundStyle(accent.palette.muted)
                    Text(s.averageHint).font(.caption).foregroundStyle(accent.palette.muted)
                    Text(s.daily).font(.title3.weight(.semibold)).foregroundStyle(accent.palette.ink).padding(.top, 24)
                    if report.started == 0, report.resolved == 0 {
                        Text(s.noActivity).font(.subheadline).foregroundStyle(accent.palette.muted)
                    } else {
                        let rows = report.byDay.compactMap { day -> (Date, String, Int)? in Reports.date(day.date).map { ($0, s.started, day.started) } }
                            + report.byDay.compactMap { day -> (Date, String, Int)? in Reports.date(day.date).map { ($0, s.resolved, day.resolved) } }
                        Chart {
                            ForEach(Array(rows.enumerated()), id: \.offset) { _, row in
                                BarMark(x: .value("Day", row.0, unit: .day), y: .value("Count", row.2))
                                    .foregroundStyle(by: .value("Series", row.1))
                                    .position(by: .value("Series", row.1))
                                    .cornerRadius(2)
                                    .opacity(selectedDay == nil || Calendar.current.isDate(selectedDay!, inSameDayAs: row.0) ? 1 : 0.35)
                            }
                            if let selectedDay, let day = report.byDay.first(where: { Reports.date($0.date).map { Calendar.current.isDate($0, inSameDayAs: selectedDay) } ?? false }) {
                                RuleMark(x: .value("Day", selectedDay, unit: .day))
                                    .foregroundStyle(accent.palette.line)
                                    .annotation(position: .top, overflowResolution: .init(x: .fit(to: .chart), y: .disabled)) {
                                        VStack(alignment: .leading, spacing: 3) {
                                            Text(Reports.dayLabel(day.date)).font(.caption.weight(.bold)).foregroundStyle(accent.palette.ink)
                                            HStack(spacing: 5) { Circle().fill(accent.color).frame(width: 7, height: 7); Text("\(s.started): \(day.started)").font(.caption) }
                                            HStack(spacing: 5) { Circle().fill(Theme.onlineGreen).frame(width: 7, height: 7); Text("\(s.resolved): \(day.resolved)").font(.caption) }
                                        }
                                        .foregroundStyle(accent.palette.ink)
                                        .padding(8)
                                        .background(accent.palette.surface, in: RoundedRectangle(cornerRadius: 8, style: .continuous))
                                        .overlay(RoundedRectangle(cornerRadius: 8, style: .continuous).strokeBorder(accent.palette.line, lineWidth: 0.5))
                                    }
                            }
                        }
                        .chartXSelection(value: $selectedDay)
                        .chartForegroundStyleScale([s.started: accent.color, s.resolved: Theme.onlineGreen])
                        .chartXAxis {
                            AxisMarks(values: .stride(by: .day, count: span <= 7 ? 1 : span <= 31 ? 5 : span <= 100 ? 15 : 30)) { _ in
                                AxisGridLine().foregroundStyle(accent.palette.line)
                                AxisValueLabel(format: .dateTime.day().month(.abbreviated)).foregroundStyle(accent.palette.muted)
                            }
                        }
                        .chartYAxis {
                            AxisMarks(position: .leading) { _ in
                                AxisGridLine().foregroundStyle(accent.palette.line)
                                AxisValueLabel().foregroundStyle(accent.palette.muted)
                            }
                        }
                        .chartLegend(position: .top, alignment: .leading)
                        .frame(height: 240)
                        .padding(16)
                        .padding(.top, 8)
                        .background(accent.palette.raised, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
                        .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).strokeBorder(accent.palette.line, lineWidth: 0.5))
                    }
                    Text(s.channelActivity).font(.title3.weight(.semibold)).foregroundStyle(accent.palette.ink).padding(.top, 24)
                    if report.byChannel.isEmpty { Text(s.noActivity).foregroundStyle(accent.palette.muted) }
                    ForEach(report.byChannel, id: \.channel) { row in
                        HStack {
                            Text(Conversations.channelName(row.channel)).foregroundStyle(accent.palette.ink)
                            Spacer()
                            Text(String(row.started)).font(.body.weight(.semibold)).foregroundStyle(accent.color)
                        }
                        .padding(.vertical, 12)
                        .overlay(alignment: .bottom) { Rectangle().fill(accent.palette.line).frame(height: 0.5) }
                    }
                    Text(s.teamActivity).font(.title3.weight(.semibold)).foregroundStyle(accent.palette.ink).padding(.top, 24)
                    ForEach(Array(report.byAgent.enumerated()), id: \.offset) { _, member in
                        Card {
                            Text(member.name.isEmpty ? s.people : member.name).font(.body.weight(.semibold)).foregroundStyle(accent.palette.ink)
                            Text("\(s.replies): \(member.replies) · \(s.assigned): \(member.assigned) · \(s.openNow): \(member.openNow)").font(.caption).foregroundStyle(accent.palette.muted)
                        }
                    }
                }
            }
            .padding(20)
        }
        .refreshable { reload += 1 }
        .task(id: "\(range.from)|\(range.to)|\(channel)|\(team)|\(reload)") {
            loading = true
            report = nil
            error = nil
            if teams.isEmpty { teams = (try? await PortalAPI.teams(server, session)) ?? [] }
            do {
                var filters = range
                filters.channel = channel.isEmpty ? nil : channel
                filters.teamId = team.isEmpty ? nil : team
                report = try await PortalAPI.report(server, session, filters)
            } catch is CancellationError {
                return
            } catch {
                if let api = error as? APIError { if api.isUnauthorized { model.expireSession() }; self.error = api.message }
                else { self.error = s.loadFailed }
            }
            loading = false
        }
    }
}

extension ReportsPanel {
    /// A dropdown that reads as a filter chip, filled when a value is chosen.
    func filterMenu<Content: View>(label: String, symbol: String, active: Bool, @ViewBuilder content: () -> Content) -> some View {
        Menu { content() } label: {
            HStack(spacing: 6) {
                Image(systemName: symbol).font(.system(size: 13))
                Text(label).font(.subheadline.weight(.semibold)).lineLimit(1)
                Image(systemName: "chevron.down").font(.system(size: 11, weight: .semibold))
            }
            .foregroundStyle(active ? accent.color : accent.palette.ink)
            .padding(.horizontal, 12)
            .frame(maxWidth: .infinity, minHeight: 38)
            .background(active ? accent.tint() : accent.palette.canvas, in: Capsule())
        }
    }
}

/// Wraps chips onto as many lines as they need.
struct FlowLayout: Layout {
    var spacing: CGFloat = 8

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let width = proposal.width ?? .infinity
        var x: CGFloat = 0, y: CGFloat = 0, rowHeight: CGFloat = 0
        for subview in subviews {
            let size = subview.sizeThatFits(.unspecified)
            if x + size.width > width, x > 0 { x = 0; y += rowHeight + spacing; rowHeight = 0 }
            x += size.width + spacing
            rowHeight = max(rowHeight, size.height)
        }
        return CGSize(width: width == .infinity ? x : width, height: y + rowHeight)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        var x = bounds.minX, y = bounds.minY, rowHeight: CGFloat = 0
        for subview in subviews {
            let size = subview.sizeThatFits(.unspecified)
            if x + size.width > bounds.maxX, x > bounds.minX { x = bounds.minX; y += rowHeight + spacing; rowHeight = 0 }
            subview.place(at: CGPoint(x: x, y: y), proposal: ProposedViewSize(size))
            x += size.width + spacing
            rowHeight = max(rowHeight, size.height)
        }
    }
}
