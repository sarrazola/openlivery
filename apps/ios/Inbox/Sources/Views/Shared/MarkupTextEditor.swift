import SwiftUI
import UIKit

/// A multi-line editor that knows where the cursor is, so a toolbar can wrap the
/// selection in WhatsApp markup or drop a variable at the insertion point.
struct MarkupTextEditor: UIViewRepresentable {
    @Binding var text: String
    var placeholder = ""
    var disabled = false
    var minHeight: CGFloat = 140
    /// Set by the toolbar; consumed once.
    @Binding var command: Command?

    enum Command: Equatable {
        case wrap(String)
        case insert(String)
    }

    func makeUIView(context: Context) -> UITextView {
        let view = UITextView()
        view.delegate = context.coordinator
        view.font = .preferredFont(forTextStyle: .body)
        view.backgroundColor = .clear
        view.textContainerInset = UIEdgeInsets(top: 12, left: 10, bottom: 12, right: 10)
        view.isScrollEnabled = true
        view.autocorrectionType = .default
        context.coordinator.placeholder.text = placeholder
        context.coordinator.placeholder.font = view.font
        context.coordinator.placeholder.textColor = .placeholderText
        context.coordinator.placeholder.numberOfLines = 0
        context.coordinator.placeholder.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(context.coordinator.placeholder)
        NSLayoutConstraint.activate([
            context.coordinator.placeholder.topAnchor.constraint(equalTo: view.topAnchor, constant: 12),
            context.coordinator.placeholder.leadingAnchor.constraint(equalTo: view.leadingAnchor, constant: 15),
            context.coordinator.placeholder.widthAnchor.constraint(equalTo: view.widthAnchor, constant: -30),
        ])
        return view
    }

    func updateUIView(_ view: UITextView, context: Context) {
        if view.text != text { view.text = text }
        view.isEditable = !disabled
        context.coordinator.placeholder.isHidden = !text.isEmpty
        context.coordinator.placeholder.text = placeholder
        if let command {
            context.coordinator.apply(command, to: view)
            DispatchQueue.main.async { self.command = nil }
        }
    }

    func sizeThatFits(_ proposal: ProposedViewSize, uiView: UITextView, context: Context) -> CGSize? {
        CGSize(width: proposal.width ?? 320, height: minHeight)
    }

    func makeCoordinator() -> Coordinator { Coordinator(text: $text) }

    final class Coordinator: NSObject, UITextViewDelegate {
        let text: Binding<String>
        let placeholder = UILabel()
        init(text: Binding<String>) { self.text = text }

        func textViewDidChange(_ view: UITextView) {
            text.wrappedValue = view.text
            placeholder.isHidden = !view.text.isEmpty
        }

        func apply(_ command: Command, to view: UITextView) {
            let range = view.selectedRange
            let current = view.text as NSString
            switch command {
            case .wrap(let marker):
                let selected = current.substring(with: range)
                let replacement = "\(marker)\(selected)\(marker)"
                view.text = current.replacingCharacters(in: range, with: replacement)
                view.selectedRange = NSRange(location: range.location + marker.count, length: selected.utf16.count)
            case .insert(let snippet):
                view.text = current.replacingCharacters(in: range, with: snippet)
                view.selectedRange = NSRange(location: range.location + (snippet as NSString).length, length: 0)
            }
            text.wrappedValue = view.text
            placeholder.isHidden = !view.text.isEmpty
            view.becomeFirstResponder()
        }
    }
}
