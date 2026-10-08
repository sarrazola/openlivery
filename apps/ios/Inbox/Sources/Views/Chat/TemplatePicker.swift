import SwiftUI

/// Choosing an approved WhatsApp template and filling what it needs.
struct TemplatePicker: View {
    let server: String
    let session: Session
    var contact = TemplateContactValues()
    var externalError: String? = nil
    let onClose: () -> Void
    let onSend: (TemplateSend) async -> Bool
    @Environment(\.accent) private var accent
    @State private var items: [Template] = []
    @State private var draft: TemplateSendDraft?
    @State private var loading = false
    @State private var busy = false
    @State private var error: String?
    @State private var attempt = 0

    var body: some View {
        let c = ChatStrings.current
        SheetScaffold(title: c.templates, closeDisabled: busy, onClose: onClose) {
            if loading {
                ProgressView().tint(accent.color).frame(maxWidth: .infinity).padding(24)
            } else if items.isEmpty, error == nil {
                Text(c.noTemplates).font(.subheadline).foregroundStyle(accent.palette.muted).padding(8)
            } else {
                ForEach(items, id: \.listId) { item in
                    ActionRow(label: item.name, subtitle: item.language, selected: draft?.template.listId == item.listId, disabled: busy) {
                        draft = TemplateSendDraft(template: item, contact: contact)
                    }
                }
            }
            if let draft {
                VStack(alignment: .leading, spacing: 12) {
                    TemplateSendForm(draft: draft, disabled: busy)
                    ActionRow(label: busy ? c.pending : c.sendTemplate, symbol: "paperplane", disabled: busy || !draft.isComplete, filled: true) {
                        Task {
                            busy = true
                            error = nil
                            if await onSend(draft.payload) { onClose() } else { error = c.updateFailed }
                            busy = false
                        }
                    }
                }
                .padding(.top, 14)
            }
            if let message = externalError ?? error {
                Text(message).foregroundStyle(accent.palette.danger).padding(.vertical, 12)
                if draft == nil { ActionRow(label: c.retry) { attempt += 1 } }
            }
        }
        .task(id: attempt) {
            loading = true
            error = nil
            draft = nil
            do { items = try await PortalAPI.templates(server, session).filter { $0.status == "APPROVED" } }
            catch { self.error = (error as? APIError)?.message ?? c.loadFailed }
            loading = false
        }
    }
}
