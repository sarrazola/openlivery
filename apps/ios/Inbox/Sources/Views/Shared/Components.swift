import SwiftUI

/// Small pieces every screen shares: avatars, rows, fields, notices.

struct Avatar: View {
    let name: String
    var size: CGFloat = 48
    var radius: CGFloat = 18
    var fontSize: CGFloat = 19
    @Environment(\.accent) private var accent

    var body: some View {
        Text(Conversations.initial(name))
            .font(.system(size: fontSize, weight: .semibold))
            .foregroundStyle(accent.color)
            .frame(width: size, height: size)
            .background(accent.tint(), in: RoundedRectangle(cornerRadius: radius, style: .continuous))
    }
}

/// A tappable row inside a sheet: label, optional subtitle and glyph, selected state.
struct ActionRow: View {
    let label: String
    var subtitle: String? = nil
    var symbol: String? = nil
    var selected = false
    var disabled = false
    var filled = false
    let action: () -> Void
    @Environment(\.accent) private var accent

    var body: some View {
        let color = filled ? accent.onColor : accent.palette.ink
        Button(action: action) {
            HStack(spacing: 12) {
                if let symbol { Image(systemName: symbol).font(.system(size: 18)).foregroundStyle(filled ? color : accent.color).frame(width: 22) }
                VStack(alignment: .leading, spacing: 3) {
                    Text(label).font(.subheadline.weight(.semibold)).foregroundStyle(color).multilineTextAlignment(.leading)
                    if let subtitle, !subtitle.isEmpty {
                        Text(subtitle).font(.caption).foregroundStyle(filled ? color : accent.palette.muted).multilineTextAlignment(.leading)
                    }
                }
                Spacer(minLength: 0)
                if selected { Image(systemName: "checkmark").foregroundStyle(accent.color) }
            }
            .padding(13)
            .frame(maxWidth: .infinity, minHeight: 50)
            .background(filled ? accent.color : selected ? accent.tint() : accent.palette.raised, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).strokeBorder(selected ? accent.color : accent.palette.line, lineWidth: 0.5))
        }
        .buttonStyle(.plain)
        .disabled(disabled)
        .opacity(disabled ? 0.55 : 1)
    }
}

struct ErrorNotice: View {
    let message: String
    var retryLabel: String = Strings.current.inbox.retry
    var retry: (() -> Void)? = nil
    var dismiss: (() -> Void)? = nil
    @Environment(\.accent) private var accent

    var body: some View {
        HStack(spacing: 10) {
            Text(message).font(.footnote).foregroundStyle(accent.palette.danger).frame(maxWidth: .infinity, alignment: .leading)
            if let retry { Button(retryLabel, action: retry).font(.footnote.weight(.semibold)).foregroundStyle(accent.color) }
            if let dismiss { Button(action: dismiss) { Image(systemName: "xmark").foregroundStyle(accent.palette.muted) }.accessibilityLabel(ChatStrings.current.close) }
        }
        .padding(12)
        .background(Theme.tint("#d95757", 0.12), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
        .accessibilityElement(children: .combine)
    }
}

struct SearchField: View {
    @Binding var text: String
    let placeholder: String
    @Environment(\.accent) private var accent

    var body: some View {
        HStack(spacing: 9) {
            Image(systemName: "magnifyingglass").foregroundStyle(accent.palette.muted)
            TextField(placeholder, text: $text)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled()
                .submitLabel(.search)
                .foregroundStyle(accent.palette.ink)
                .accessibilityLabel(placeholder)
            if !text.isEmpty {
                Button { text = "" } label: { Image(systemName: "xmark.circle.fill").foregroundStyle(accent.palette.muted) }
                    .accessibilityLabel(Strings.current.inbox.clearFilters)
            }
        }
        .padding(.horizontal, 12)
        .frame(height: 44)
        .background(accent.palette.canvas, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
    }
}

struct PrimaryButton: View {
    let label: String
    var busy = false
    var disabled = false
    var brandHex: String? = nil
    let action: () -> Void
    @Environment(\.accent) private var accent

    var body: some View {
        let hex = brandHex ?? accent.hex
        Button(action: action) {
            ZStack {
                Text(label).font(.body.weight(.semibold)).foregroundStyle(Theme.contrastOn(hex)).opacity(busy ? 0 : 1)
                if busy { ProgressView().tint(Theme.contrastOn(hex)) }
            }
            .frame(maxWidth: .infinity, minHeight: 50)
            .background(Color(hex: hex), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
        }
        .buttonStyle(.plain)
        .disabled(disabled || busy)
        .opacity(disabled ? 0.65 : 1)
    }
}

/// A password field with a control to reveal what was typed.
struct PasswordField: View {
    @Binding var text: String
    var placeholder = "••••••••"
    var disabled = false
    var accessibilityLabel: String? = nil
    var onSubmit: (() -> Void)? = nil
    @State private var revealed = false
    @FocusState private var focus: Bool
    @Environment(\.accent) private var accent

    var body: some View {
        HStack(spacing: 8) {
            Group {
                if revealed {
                    TextField(placeholder, text: $text)
                } else {
                    SecureField(placeholder, text: $text)
                }
            }
            .textContentType(.password)
            .textInputAutocapitalization(.never)
            .autocorrectionDisabled()
            .submitLabel(.go)
            .onSubmit { onSubmit?() }
            .focused($focus)
            .foregroundStyle(accent.palette.ink)
            Button { revealed.toggle(); focus = true } label: {
                Image(systemName: revealed ? "eye.slash" : "eye").foregroundStyle(accent.palette.muted).frame(width: 32, height: 32)
            }
            .accessibilityLabel(revealed ? "Hide password" : "Show password")
        }
        .padding(.leading, 14)
        .padding(.trailing, 8)
        .frame(minHeight: 48)
        .background(accent.palette.raised, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 10, style: .continuous).strokeBorder(accent.palette.line, lineWidth: 0.5))
        .disabled(disabled)
        .accessibilityLabel(accessibilityLabel ?? placeholder)
    }
}

struct FieldLabel: View {
    let text: String
    @Environment(\.accent) private var accent
    var body: some View { Text(text).font(.footnote.weight(.semibold)).foregroundStyle(accent.palette.ink) }
}

/// A bordered text field in the form style every screen uses.
struct FormTextField: View {
    @Binding var text: String
    var placeholder = ""
    var keyboard: UIKeyboardType = .default
    var multiline = false
    var disabled = false
    var contentType: UITextContentType? = nil
    var autocapitalize: TextInputAutocapitalization = .sentences
    var secure = false
    var accessibilityLabel: String? = nil
    var onSubmit: (() -> Void)? = nil
    @Environment(\.accent) private var accent

    var body: some View {
        Group {
            if secure {
                SecureField(placeholder, text: $text).textContentType(contentType).submitLabel(.go).onSubmit { onSubmit?() }
            } else if multiline {
                TextField(placeholder, text: $text, axis: .vertical).lineLimit(4...10)
            } else {
                TextField(placeholder, text: $text).submitLabel(.next).onSubmit { onSubmit?() }
            }
        }
        .keyboardType(keyboard)
        .textContentType(contentType)
        .textInputAutocapitalization(autocapitalize)
        .autocorrectionDisabled(keyboard == .emailAddress || keyboard == .URL || secure)
        .foregroundStyle(accent.palette.ink)
        .padding(.horizontal, 14)
        .padding(.vertical, multiline ? 12 : 0)
        .frame(minHeight: 48, alignment: multiline ? .topLeading : .center)
        .background(accent.palette.raised, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 10, style: .continuous).strokeBorder(accent.palette.line, lineWidth: 0.5))
        .disabled(disabled)
        .accessibilityLabel(accessibilityLabel ?? placeholder)
    }
}

/// A rounded chip, filled with the brand tint when selected.
struct Pill: View {
    let label: String
    var symbol: String? = nil
    var count: String? = nil
    var expand = false
    let selected: Bool
    let action: () -> Void
    @Environment(\.accent) private var accent

    var body: some View {
        Button(action: action) {
            HStack(spacing: 6) {
                if let symbol { Image(systemName: symbol).font(.system(size: 13)) }
                Text(label).font(.subheadline.weight(.semibold)).lineLimit(1)
                if let count { Text(count).font(.caption2.weight(.bold)) }
            }
            .foregroundStyle(selected ? accent.color : accent.palette.muted)
            .padding(.horizontal, 12)
            .frame(maxWidth: expand ? .infinity : nil, minHeight: 38)
            .background(selected ? accent.tint() : accent.palette.canvas, in: Capsule())
        }
        .buttonStyle(.plain)
    }
}

/// A modal with a title, a close control and scrolling content.
struct SheetScaffold<Content: View>: View {
    let title: String
    var closeDisabled = false
    let onClose: () -> Void
    @ViewBuilder let content: () -> Content
    @Environment(\.accent) private var accent

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 8) { content() }
                    .padding(18)
            }
            .scrollDismissesKeyboard(.interactively)
            .background(accent.palette.surface)
            .navigationTitle(title)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button(action: onClose) { Image(systemName: "xmark").foregroundStyle(accent.palette.muted) }
                        .disabled(closeDisabled)
                        .accessibilityLabel(ChatStrings.current.close)
                }
            }
        }
        .tint(accent.color)
    }
}

/// Press highlight for list rows drawn by hand.
struct RowButtonStyle: ButtonStyle {
    let palette: Palette
    var unreadTint: Color? = nil
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .background(configuration.isPressed ? palette.pressed : (unreadTint ?? palette.surface))
    }
}

struct SectionTitle: View {
    let text: String
    @Environment(\.accent) private var accent
    var body: some View { Text(text).font(.headline).foregroundStyle(accent.palette.ink).padding(.top, 14).padding(.bottom, 4) }
}

struct Card<Content: View>: View {
    @ViewBuilder let content: () -> Content
    @Environment(\.accent) private var accent
    var body: some View {
        VStack(alignment: .leading, spacing: 9) { content() }
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(accent.palette.raised, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).strokeBorder(accent.palette.line, lineWidth: 0.5))
    }
}

/// A radio or checkbox row for editors.
struct ChoiceRow: View {
    let label: String
    var subtitle: String? = nil
    let selected: Bool
    var checkbox = false
    var disabled = false
    let action: () -> Void
    @Environment(\.accent) private var accent

    var body: some View {
        Button(action: action) {
            HStack(spacing: 12) {
                Image(systemName: checkbox ? (selected ? "checkmark.square.fill" : "square") : (selected ? "largecircle.fill.circle" : "circle"))
                    .font(.system(size: 22)).foregroundStyle(accent.color)
                VStack(alignment: .leading, spacing: 4) {
                    Text(label).font(.body.weight(.semibold)).foregroundStyle(accent.palette.ink)
                    if let subtitle, !subtitle.isEmpty { Text(subtitle).font(.caption).foregroundStyle(accent.palette.muted) }
                }
                Spacer(minLength: 0)
            }
            .padding(12)
            .background(selected && !checkbox ? accent.tint(0.08) : accent.palette.surface, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).strokeBorder(selected && !checkbox ? accent.color : accent.palette.line, lineWidth: 1))
        }
        .buttonStyle(.plain)
        .disabled(disabled)
        .accessibilityAddTraits(selected ? .isSelected : [])
    }
}

/// Opens a link in the system browser and reports failure through an alert binding.
@MainActor
func openExternal(_ url: URL, failure: Binding<AppModel.AlertContent?>) {
    UIApplication.shared.open(url, options: [:]) { ok in
        if !ok { failure.wrappedValue = AppModel.AlertContent(title: PrivacyStrings.current.linkFailed, message: nil) }
    }
}
