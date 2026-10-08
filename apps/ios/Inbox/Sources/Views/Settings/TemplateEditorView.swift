import PhotosUI
import SwiftUI
import UniformTypeIdentifiers

/// Creating a WhatsApp template the way the web does: header, message with
/// markup and variables, footer and buttons, with a preview and the samples
/// Meta reviews it with.
struct TemplateEditorView: View {
    let server: String
    let session: Session
    let onSaved: () -> Void
    @Environment(\.dismiss) private var dismiss
    @Environment(\.accent) private var accent
    @State private var name = ""
    @State private var language = AppLocale.languageCode
    @State private var category = "UTILITY"
    @State private var headerFormat = "NONE"
    @State private var headerText = ""
    @State private var sample: Sample?
    @State private var uploading = false
    @State private var messageBody = ""
    @State private var footer = ""
    @State private var buttons: [DraftButton] = []
    @State private var examples: [String: String] = [:]
    @State private var command: MarkupTextEditor.Command?
    @State private var askVariable = false
    @State private var variableName = ""
    @State private var photoItem: PhotosPickerItem?
    @State private var showPhotos = false
    @State private var showFiles = false
    @State private var busy = false
    @State private var error: String?

    struct Sample: Equatable { var name: String; var handle: String; var image: UIImage? }
    struct DraftButton: Identifiable, Equatable {
        let id = UUID()
        var type = "QUICK_REPLY"
        var text = ""
        var url = ""
        var phone = ""
        var example = ""
    }

    private static let limits = (header: 60, body: 1024, footer: 60, button: 25, url: 2000, code: 15, buttons: 10)
    private static let headerFormats = ["NONE", "TEXT", "IMAGE", "VIDEO", "DOCUMENT", "LOCATION"]
    private static let contactExamples = ["contact_name": "María", "contact_phone": "+57 300 123 4567", "contact_email": "maria@correo.com", "agent_name": "Ana"]

    private var mediaHeader: Bool { ["IMAGE", "VIDEO", "DOCUMENT"].contains(headerFormat) }

    private func names(in text: String) -> [String] {
        var seen: [String] = []
        for match in text.matches(of: /\{\{([a-z0-9_]+)\}\}/) where !seen.contains(String(match.1)) { seen.append(String(match.1)) }
        return seen
    }

    private var headerNames: [String] { headerFormat == "TEXT" ? names(in: headerText) : [] }
    private var bodyNames: [String] { names(in: messageBody) }
    /// Contact variables bring their own review sample; only custom ones are asked for.
    private var customNames: [String] { (headerNames + bodyNames).filter { !TemplateContactValues.variables.contains($0) }.reduce(into: []) { if !$0.contains($1) { $0.append($1) } } }

    private var problems: [String] {
        var out: [String] = []
        if name.range(of: "^[a-z0-9_]{1,512}$", options: .regularExpression) == nil { out.append("name") }
        if messageBody.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || messageBody.count > TemplateEditorView.limits.body { out.append("body") }
        if headerFormat == "TEXT", headerText.trimmingCharacters(in: .whitespaces).isEmpty || headerText.count > TemplateEditorView.limits.header || headerNames.count > 1 { out.append("header") }
        if mediaHeader, sample == nil { out.append("sample") }
        if footer.count > TemplateEditorView.limits.footer { out.append("footer") }
        if buttons.count > TemplateEditorView.limits.buttons { out.append("buttons") }
        for button in buttons {
            if button.text.trimmingCharacters(in: .whitespaces).isEmpty || button.text.count > TemplateEditorView.limits.button { out.append("button") }
            if button.type == "URL", !button.url.lowercased().hasPrefix("https://") || button.url.count > TemplateEditorView.limits.url { out.append("url") }
            if button.type == "URL", button.url.contains("{{1}}"), button.example.trimmingCharacters(in: .whitespaces).isEmpty { out.append("urlExample") }
            if button.type == "PHONE_NUMBER", button.phone.filter(\.isNumber).count < 7 { out.append("phone") }
            if button.type == "COPY_CODE", button.example.trimmingCharacters(in: .whitespaces).isEmpty || button.example.count > TemplateEditorView.limits.code { out.append("code") }
        }
        if customNames.contains(where: { (examples[$0] ?? "").trimmingCharacters(in: .whitespaces).isEmpty }) { out.append("examples") }
        return out
    }

    var body: some View {
        let s = SettingsStrings.current
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 8) {
                    FieldLabel(text: s.templateName).padding(.top, 12)
                    FormTextField(text: $name, placeholder: "pedido_listo", disabled: busy, autocapitalize: .never, accessibilityLabel: s.templateName)
                    Text(s.templateNameHint).font(.footnote).foregroundStyle(accent.palette.muted)
                    FieldLabel(text: s.language).padding(.top, 12)
                    Picker("", selection: $language) { Text("Español").tag("es"); Text("English").tag("en") }.pickerStyle(.segmented)
                    FieldLabel(text: s.category).padding(.top, 12)
                    Picker("", selection: $category) { Text(s.utility).tag("UTILITY"); Text(s.marketing).tag("MARKETING") }.pickerStyle(.segmented)

                    FieldLabel(text: s.header).padding(.top, 12)
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack(spacing: 6) {
                            ForEach(TemplateEditorView.headerFormats, id: \.self) { format in
                                Pill(label: headerLabel(format), symbol: headerSymbol(format), selected: headerFormat == format) {
                                    headerFormat = format
                                    if !mediaHeader { sample = nil }
                                }
                            }
                        }
                    }
                    if headerFormat == "TEXT" {
                        FormTextField(text: $headerText, disabled: busy, accessibilityLabel: s.headerText)
                        Text(s.headerTextHint).font(.footnote).foregroundStyle(accent.palette.muted)
                    }
                    if mediaHeader { samplePicker }

                    FieldLabel(text: s.body).padding(.top, 12)
                    MarkupTextEditor(text: $messageBody, placeholder: "Hola {{nombre}}, tu pedido {{pedido}} está listo.", disabled: busy, command: $command)
                        .background(accent.palette.raised, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
                        .overlay(RoundedRectangle(cornerRadius: 10, style: .continuous).strokeBorder(accent.palette.line, lineWidth: 0.5))
                    HStack(spacing: 6) {
                        markupButton("bold", s.bold) { command = .wrap("*") }
                        markupButton("italic", s.italic) { command = .wrap("_") }
                        markupButton("strikethrough", s.strike) { command = .wrap("~") }
                        markupButton("chevron.left.forwardslash.chevron.right", s.code) { command = .wrap("```") }
                        Spacer()
                        Button { variableName = ""; askVariable = true } label: {
                            HStack(spacing: 4) { Image(systemName: "plus"); Text(s.addVariable) }.font(.footnote.weight(.semibold)).foregroundStyle(accent.color)
                        }
                    }
                    Text("\(messageBody.count)/\(TemplateEditorView.limits.body)").font(.caption2).foregroundStyle(accent.palette.muted)
                    Text(s.contactVariablesHint).font(.footnote).foregroundStyle(accent.palette.muted)
                    FlowLayout(spacing: 6) {
                        ForEach(TemplateContactValues.variables, id: \.self) { variable in
                            Button { command = .insert("{{\(variable)}}") } label: {
                                Text("{{\(variable)}}").font(.system(.caption, design: .monospaced)).foregroundStyle(accent.color)
                                    .padding(.horizontal, 8).padding(.vertical, 5).background(accent.tint(0.08), in: RoundedRectangle(cornerRadius: 6))
                            }
                        }
                    }
                    Text(s.customVariableHint).font(.footnote).foregroundStyle(accent.palette.muted)
                    ForEach(customNames, id: \.self) { variable in
                        FieldLabel(text: "\(s.example) {{\(variable)}}").padding(.top, 8)
                        FormTextField(text: Binding(get: { examples[variable] ?? "" }, set: { examples[variable] = $0 }), disabled: busy, accessibilityLabel: "\(s.example) \(variable)")
                    }
                    if !customNames.isEmpty { Text(s.examplesHint).font(.footnote).foregroundStyle(accent.palette.muted) }

                    FieldLabel(text: s.footer).padding(.top, 12)
                    FormTextField(text: $footer, placeholder: "Responde BAJA para no recibir más mensajes.", disabled: busy, accessibilityLabel: s.footer)

                    FieldLabel(text: s.buttons).padding(.top, 12)
                    ForEach($buttons) { $button in buttonEditor($button) }
                    if buttons.count < TemplateEditorView.limits.buttons {
                        Menu {
                            Button(s.quickReply) { buttons.append(DraftButton(type: "QUICK_REPLY")) }
                            Button(s.urlButton) { buttons.append(DraftButton(type: "URL")) }
                            Button(s.phoneButton) { buttons.append(DraftButton(type: "PHONE_NUMBER")) }
                            Button(s.copyCode) { buttons.append(DraftButton(type: "COPY_CODE")) }
                        } label: {
                            HStack { Image(systemName: "plus"); Text(s.addButton); Spacer(); Image(systemName: "chevron.down") }
                                .font(.subheadline.weight(.semibold)).foregroundStyle(accent.color).padding(13)
                                .background(accent.tint(0.08), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                        }
                    }

                    preview.padding(.top, 16)
                    if let error { Text(error).foregroundStyle(accent.palette.danger) }
                    PrimaryButton(label: s.submit, busy: busy, disabled: !problems.isEmpty || uploading) { Task { await save() } }.padding(.top, 20)
                }
                .padding(22)
            }
            .scrollDismissesKeyboard(.interactively)
            .background(accent.palette.surface)
            .navigationTitle(s.newTemplate)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .topBarLeading) { Button(s.cancel) { dismiss() }.disabled(busy) } }
            .alert(s.variableName, isPresented: $askVariable) {
                TextField("nombre", text: $variableName).textInputAutocapitalization(.never).autocorrectionDisabled()
                Button(s.addVariable) {
                    let cleaned = variableName.lowercased().replacingOccurrences(of: " ", with: "_").filter { $0.isLetter || $0.isNumber || $0 == "_" }
                    if !cleaned.isEmpty { command = .insert("{{\(cleaned)}}") }
                }
                Button(s.cancel, role: .cancel) {}
            }
            .photosPicker(isPresented: $showPhotos, selection: $photoItem, matching: headerFormat == "VIDEO" ? .videos : .images)
            .onChange(of: photoItem) { _, item in
                guard let item else { return }
                Task { await importPhoto(item); photoItem = nil }
            }
            .fileImporter(isPresented: $showFiles, allowedContentTypes: [.pdf]) { result in
                if case .success(let url) = result { Task { await importFile(url) } }
            }
        }
        .tint(accent.color)
    }

    private func headerLabel(_ format: String) -> String {
        let s = SettingsStrings.current
        switch format {
        case "TEXT": return s.headerText
        case "IMAGE": return s.headerImage
        case "VIDEO": return s.headerVideo
        case "DOCUMENT": return s.headerDocument
        case "LOCATION": return s.headerLocation
        default: return s.headerNone
        }
    }

    private func headerSymbol(_ format: String) -> String? {
        switch format {
        case "TEXT": return "textformat"
        case "IMAGE": return "photo"
        case "VIDEO": return "video"
        case "DOCUMENT": return "doc.text"
        case "LOCATION": return "mappin.and.ellipse"
        default: return nil
        }
    }

    private func markupButton(_ symbol: String, _ label: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Image(systemName: symbol).font(.system(size: 14, weight: .semibold)).foregroundStyle(accent.palette.ink)
                .frame(width: 36, height: 32)
                .background(accent.palette.canvas, in: RoundedRectangle(cornerRadius: 8, style: .continuous))
        }
        .accessibilityLabel(label)
    }

    private var samplePicker: some View {
        let s = SettingsStrings.current
        return VStack(alignment: .leading, spacing: 8) {
            Button {
                if headerFormat == "DOCUMENT" { showFiles = true } else { showPhotos = true }
            } label: {
                HStack(spacing: 10) {
                    if let image = sample?.image {
                        Image(uiImage: image).resizable().scaledToFill().frame(width: 44, height: 44).clipShape(RoundedRectangle(cornerRadius: 8))
                    } else {
                        Image(systemName: headerSymbol(headerFormat) ?? "doc").foregroundStyle(accent.color).frame(width: 44, height: 44)
                    }
                    VStack(alignment: .leading, spacing: 2) {
                        Text(uploading ? s.uploading : (sample?.name ?? s.chooseSample)).font(.subheadline.weight(.semibold)).foregroundStyle(accent.palette.ink).lineLimit(1)
                        Text(s.sampleHint).font(.caption).foregroundStyle(accent.palette.muted)
                    }
                    Spacer()
                    if uploading { ProgressView().tint(accent.color) }
                }
                .padding(12)
                .background(accent.palette.canvas, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
            }
            .buttonStyle(.plain)
            .disabled(busy || uploading)
        }
    }

    private func buttonEditor(_ button: Binding<DraftButton>) -> some View {
        let s = SettingsStrings.current
        let type = button.wrappedValue.type
        let title = type == "URL" ? s.urlButton : type == "PHONE_NUMBER" ? s.phoneButton : type == "COPY_CODE" ? s.copyCode : s.quickReply
        return VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(title).font(.subheadline.weight(.semibold)).foregroundStyle(accent.palette.ink)
                Spacer()
                Button { buttons.removeAll { $0.id == button.wrappedValue.id } } label: { Image(systemName: "trash").foregroundStyle(accent.palette.danger) }
                    .accessibilityLabel(s.delete)
            }
            if type != "COPY_CODE" {
                FormTextField(text: button.text, placeholder: s.buttonText, disabled: busy, accessibilityLabel: s.buttonText)
            }
            if type == "URL" {
                FormTextField(text: button.url, placeholder: "https://", keyboard: .URL, disabled: busy, autocapitalize: .never, accessibilityLabel: s.buttonUrl)
                Text(s.buttonUrlHint).font(.caption).foregroundStyle(accent.palette.muted)
                if button.wrappedValue.url.contains("{{1}}") {
                    FormTextField(text: button.example, placeholder: s.buttonExample, disabled: busy, autocapitalize: .never, accessibilityLabel: s.buttonExample)
                }
            }
            if type == "PHONE_NUMBER" {
                FormTextField(text: button.phone, placeholder: "+57 300 123 4567", keyboard: .phonePad, disabled: busy, accessibilityLabel: s.buttonPhone)
            }
            if type == "COPY_CODE" {
                FormTextField(text: button.example, placeholder: s.codeExample, disabled: busy, autocapitalize: .never, accessibilityLabel: s.codeExample)
            }
        }
        .padding(12)
        .background(accent.palette.raised, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).strokeBorder(accent.palette.line, lineWidth: 0.5))
    }

    private var preview: some View {
        let s = SettingsStrings.current
        var text = messageBody
        var header = headerText
        for (key, value) in TemplateEditorView.contactExamples.merging(examples) { $1 } {
            text = text.replacingOccurrences(of: "{{\(key)}}", with: value)
            header = header.replacingOccurrences(of: "{{\(key)}}", with: value)
        }
        return VStack(alignment: .leading, spacing: 8) {
            Text(s.previewTitle).font(.caption.weight(.semibold)).foregroundStyle(accent.color)
            if messageBody.isEmpty, headerFormat == "NONE" {
                Text(s.previewEmpty).font(.footnote).foregroundStyle(accent.palette.muted)
            } else {
                if headerFormat == "TEXT", !header.isEmpty { Text(header).font(.body.weight(.bold)).foregroundStyle(accent.palette.ink) }
                if mediaHeader {
                    if let image = sample?.image { Image(uiImage: image).resizable().scaledToFill().frame(height: 120).clipShape(RoundedRectangle(cornerRadius: 8)) }
                    else { RoundedRectangle(cornerRadius: 8).fill(accent.palette.canvas).frame(height: 80).overlay(Image(systemName: headerSymbol(headerFormat) ?? "doc").foregroundStyle(accent.palette.muted)) }
                }
                if headerFormat == "LOCATION" { RoundedRectangle(cornerRadius: 8).fill(accent.palette.canvas).frame(height: 80).overlay(Image(systemName: "mappin.and.ellipse").foregroundStyle(accent.palette.muted)) }
                Text(RichText.attributed(text)).foregroundStyle(accent.palette.ink)
                if !footer.isEmpty { Text(footer).font(.caption).foregroundStyle(accent.palette.muted) }
                ForEach(buttons) { button in
                    Text(button.type == "COPY_CODE" ? s.copyCode : button.text.isEmpty ? "…" : button.text).font(.subheadline.weight(.semibold)).foregroundStyle(accent.color)
                        .frame(maxWidth: .infinity, minHeight: 36)
                        .background(accent.palette.surface, in: RoundedRectangle(cornerRadius: 8, style: .continuous))
                }
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(accent.tint(0.08), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
    }

    private func importPhoto(_ item: PhotosPickerItem) async {
        guard let data = try? await item.loadTransferable(type: Data.self) else { return }
        let type = item.supportedContentTypes.first
        let ext = type?.preferredFilenameExtension ?? (headerFormat == "VIDEO" ? "mp4" : "jpg")
        let mime = type?.preferredMIMEType ?? (headerFormat == "VIDEO" ? "video/mp4" : "image/jpeg")
        let url = AttachmentCache.stagingURL(name: "sample.\(ext)")
        guard (try? data.write(to: url, options: .atomic)) != nil else { return }
        await upload(OutgoingFile(url: url, name: "sample.\(ext)", mime: mime), image: headerFormat == "IMAGE" ? UIImage(data: data) : nil)
    }

    private func importFile(_ source: URL) async {
        let access = source.startAccessingSecurityScopedResource()
        defer { if access { source.stopAccessingSecurityScopedResource() } }
        let target = AttachmentCache.stagingURL(name: source.lastPathComponent)
        guard (try? FileManager.default.copyItem(at: source, to: target)) != nil else { return }
        await upload(OutgoingFile(url: target, name: source.lastPathComponent, mime: "application/pdf"), image: nil)
    }

    private func upload(_ file: OutgoingFile, image: UIImage?) async {
        uploading = true
        error = nil
        defer { uploading = false }
        do {
            let result = try await PortalAPI.uploadTemplateSample(server, session, file: file)
            sample = Sample(name: file.name, handle: result.handle, image: image)
        } catch {
            self.error = (error as? APIError)?.message ?? SettingsStrings.current.saveFailed
        }
    }

    private func save() async {
        busy = true
        error = nil
        defer { busy = false }
        var samples: [String: String] = [:]
        for variable in headerNames + bodyNames {
            samples[variable] = (examples[variable] ?? TemplateEditorView.contactExamples[variable] ?? "").trimmingCharacters(in: .whitespaces)
        }
        let header: TemplateHeaderIn? = headerFormat == "NONE" ? nil : TemplateHeaderIn(
            format: headerFormat, text: headerFormat == "TEXT" ? headerText.trimmingCharacters(in: .whitespaces) : "", handle: sample?.handle ?? ""
        )
        do {
            _ = try await PortalAPI.createTemplate(server, session, TemplateCreate(
                name: name, language: language, category: category, header: header,
                body: messageBody.trimmingCharacters(in: .whitespacesAndNewlines), footer: footer.trimmingCharacters(in: .whitespaces),
                buttons: buttons.map { TemplateButtonIn(type: $0.type, text: $0.text.trimmingCharacters(in: .whitespaces), url: $0.url.trimmingCharacters(in: .whitespaces), phoneNumber: $0.phone.trimmingCharacters(in: .whitespaces), example: $0.example.trimmingCharacters(in: .whitespaces)) },
                examples: samples
            ))
            onSaved()
            dismiss()
        } catch let failure as APIError {
            error = failure.status == 409 ? SettingsStrings.current.duplicate : failure.message
        } catch { self.error = SettingsStrings.current.saveFailed }
    }
}
