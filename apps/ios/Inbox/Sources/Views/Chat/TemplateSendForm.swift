import SwiftUI

/// The contact and agent values a template variable fills itself with.
struct TemplateContactValues {
    var contactName = ""
    var contactPhone = ""
    var contactEmail = ""
    var agentName = ""

    static let variables = ["contact_name", "contact_phone", "contact_email", "agent_name"]

    func value(for name: String) -> String {
        switch name {
        case "contact_name": return contactName
        case "contact_phone": return contactPhone
        case "contact_email": return contactEmail
        case "agent_name": return agentName
        default: return ""
        }
    }
}

/// Everything a chosen template needs before it can be sent, the way the web
/// asks for it: the header's variable or media link, a location, one value per
/// body variable (named ones start filled from the contact) and a value for
/// each dynamic button. Produces the payload once nothing is missing.
@MainActor
@Observable
final class TemplateSendDraft {
    let template: Template
    var values: [String: String]
    var headerValue = ""
    var latitude = ""
    var longitude = ""
    var placeName = ""
    var address = ""
    var buttonValues: [String]

    init(template: Template, contact: TemplateContactValues) {
        self.template = template
        var filled: [String: String] = [:]
        for name in template.parameters { filled[name] = contact.value(for: name) }
        values = filled
        if let header = template.header, header.format == "TEXT", let name = header.parameters.first { headerValue = contact.value(for: name) }
        buttonValues = Array(repeating: "", count: template.buttons.count)
    }

    var headerParameter: String? {
        guard let header = template.header, header.format == "TEXT" else { return nil }
        return header.parameters.first
    }

    var mediaHeader: String? {
        guard let header = template.header, ["IMAGE", "VIDEO", "DOCUMENT"].contains(header.format) else { return nil }
        return header.format
    }

    var locationHeader: Bool { template.header?.format == "LOCATION" }

    var dynamicButtons: [(index: Int, button: TemplateButton)] {
        template.buttons.enumerated().filter { $0.element.dynamic }.map { ($0.offset, $0.element) }
    }

    private func trimmed(_ text: String) -> String { text.trimmingCharacters(in: .whitespacesAndNewlines) }

    var isComplete: Bool {
        if template.parameters.contains(where: { trimmed(values[$0] ?? "").isEmpty }) { return false }
        if headerParameter != nil, trimmed(headerValue).isEmpty { return false }
        if mediaHeader != nil, !trimmed(headerValue).lowercased().hasPrefix("https://") { return false }
        if locationHeader, Double(trimmed(latitude)) == nil || Double(trimmed(longitude)) == nil { return false }
        if dynamicButtons.contains(where: { trimmed(buttonValues[$0.index]).isEmpty }) { return false }
        return true
    }

    var payload: TemplateSend {
        TemplateSend(
            name: template.name, language: template.language,
            variables: template.parameters.map { trimmed(values[$0] ?? "") },
            headerValue: trimmed(headerValue),
            location: locationHeader ? TemplateLocation(latitude: Double(trimmed(latitude)) ?? 0, longitude: Double(trimmed(longitude)) ?? 0, name: trimmed(placeName), address: trimmed(address)) : nil,
            buttonValues: buttonValues.map(trimmed)
        )
    }

    /// The body with every variable the person has filled so far.
    var preview: String {
        var text = template.body
        for name in template.parameters {
            let value = trimmed(values[name] ?? "")
            if !value.isEmpty { text = text.replacingOccurrences(of: "{{\(name)}}", with: value) }
        }
        return text
    }
}

struct TemplateSendForm: View {
    @Bindable var draft: TemplateSendDraft
    let disabled: Bool
    @Environment(\.accent) private var accent

    var body: some View {
        let c = ChatStrings.current
        VStack(alignment: .leading, spacing: 12) {
            if let name = draft.headerParameter {
                field("\(c.templateValue) {{\(name)}}", text: $draft.headerValue)
            }
            if let kind = draft.mediaHeader {
                field(c.mediaLink.replacingOccurrences(of: "{kind}", with: kind.lowercased()), text: $draft.headerValue, keyboard: .URL, placeholder: "https://")
            }
            if draft.locationHeader {
                HStack(spacing: 10) {
                    field(c.latitude, text: $draft.latitude, keyboard: .decimalPad, placeholder: "4.6533")
                    field(c.longitude, text: $draft.longitude, keyboard: .decimalPad, placeholder: "-74.0836")
                }
                field(c.placeName, text: $draft.placeName)
                field(c.address, text: $draft.address)
            }
            ForEach(draft.template.parameters, id: \.self) { name in
                field("\(c.templateValue) {{\(name)}}", text: Binding(get: { draft.values[name] ?? "" }, set: { draft.values[name] = $0 }))
            }
            ForEach(draft.dynamicButtons, id: \.index) { item in
                field(item.button.type == "COPY_CODE" ? c.buttonCode : c.buttonLink.replacingOccurrences(of: "{text}", with: item.button.text),
                      text: $draft.buttonValues[item.index], placeholder: item.button.example)
            }
            VStack(alignment: .leading, spacing: 8) {
                Text(c.preview).font(.caption.weight(.semibold)).foregroundStyle(accent.color)
                if let header = draft.template.header, header.format == "TEXT", !header.text.isEmpty {
                    Text(draft.headerParameter.map { header.text.replacingOccurrences(of: "{{\($0)}}", with: draft.headerValue) } ?? header.text)
                        .font(.body.weight(.bold)).foregroundStyle(accent.palette.ink)
                }
                Text(RichText.attributed(draft.preview)).foregroundStyle(accent.palette.ink)
                if !draft.template.footer.isEmpty { Text(draft.template.footer).font(.caption).foregroundStyle(accent.palette.muted).padding(.top, 2) }
                ForEach(Array(draft.template.buttons.enumerated()), id: \.offset) { _, button in
                    Text(button.text).font(.subheadline.weight(.semibold)).foregroundStyle(accent.color)
                        .frame(maxWidth: .infinity, minHeight: 36)
                        .background(accent.palette.surface, in: RoundedRectangle(cornerRadius: 8, style: .continuous))
                }
            }
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(accent.tint(0.08), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
        }
    }

    private func field(_ label: String, text: Binding<String>, keyboard: UIKeyboardType = .default, placeholder: String = "") -> some View {
        VStack(alignment: .leading, spacing: 5) {
            Text(label).font(.footnote).foregroundStyle(accent.palette.muted)
            FormTextField(text: text, placeholder: placeholder, keyboard: keyboard, disabled: disabled, autocapitalize: keyboard == .URL ? .never : .sentences, accessibilityLabel: label)
        }
    }
}
