import SwiftUI

/// Inbox, contacts and workspace, each with its own navigation stack. Opening
/// a conversation pushes the thread and hides the tab bar, the way Messages does.
struct MainTabsView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.accent) private var accent

    var body: some View {
        @Bindable var model = model
        let s = Strings.current.inbox
        TabView(selection: $model.tab) {
            NavigationStack(path: $model.inboxPath) {
                ConversationsView()
                    .navigationDestination(for: Conversation.self) { conversation in
                        ChatView(conversation: conversation)
                    }
            }
            .tabItem { Label(s.title, systemImage: "bubble.left.and.bubble.right") }
            .tag(AppModel.Tab.inbox)

            NavigationStack(path: $model.contactsPath) {
                ContactsView()
                    .navigationDestination(for: Conversation.self) { conversation in
                        ChatView(conversation: conversation)
                    }
            }
            .tabItem { Label(s.contacts, systemImage: "person.2") }
            .tag(AppModel.Tab.contacts)

            if model.session?.has("reports.view") == true {
                NavigationStack {
                    ReportsView()
                }
                .tabItem { Label(WorkspaceStrings.current.reports, systemImage: "chart.bar") }
                .tag(AppModel.Tab.reports)
            }

            NavigationStack {
                SettingsView()
            }
            .tabItem { Label(SettingsStrings.current.title, systemImage: "gearshape") }
            .tag(AppModel.Tab.settings)
        }
        .tint(accent.color)
    }
}
