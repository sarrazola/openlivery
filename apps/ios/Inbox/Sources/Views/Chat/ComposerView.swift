import PhotosUI
import SwiftUI
import UniformTypeIdentifiers

/// Writing back: text, a photo, a file, or a voice note.
///
/// Saved replies sit above the message field. The attachment menu and microphone
/// sit to its left, with sending on the right. Recording replaces the whole row:
/// a level meter, the elapsed time, and delete / pause / review. Review stages
/// the audio as an attachment with playback so the person can listen before
/// sending it with their text.
struct ComposerView: View {
    let channel: String
    let capabilities: ChannelCapabilities
    let draftKey: String
    let busy: Bool
    let onSendText: (String) async -> Bool
    let onSendFile: (OutgoingFile, String) async -> Bool
    @Binding var insertedReply: String?
    var onSavedReplies: (() -> Void)? = nil
    var onAttachmentSelected: (() -> Void)? = nil
    let onError: (String) -> Void

    @Environment(\.accent) private var accent
    @Environment(\.scenePhase) private var scenePhase
    @State private var draft = ""
    @State private var pendingFile: OutgoingFile?
    @State private var sending = false
    @State private var recorder = Recorder()
    @State private var attachMenu = false
    @State private var photoItem: PhotosPickerItem?
    @State private var showPhotos = false
    @State private var showCamera = false
    @State private var showFiles = false
    @State private var alert: AppModel.AlertContent?
    @State private var loaded = false
    @FocusState private var focused: Bool

    private var textAllowed: Bool { capabilities.text == true }
    private var fileAllowed: Bool { pendingFile.map { InboxRules.acceptsAttachment(channel: channel, capabilities: capabilities, mime: $0.mime) } ?? true }
    private var canSend: Bool {
        let text = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        return fileAllowed && (text.isEmpty || textAllowed) && (!text.isEmpty || pendingFile != nil)
    }
    private var canAttach: Bool { [capabilities.image, capabilities.video, capabilities.audio, capabilities.file].contains(true) }
    private var mediaAllowed: Bool { capabilities.image == true || capabilities.video == true }

    var body: some View {
        let s = Strings.current.composer
        let c = ChatStrings.current
        VStack(spacing: 0) {
            if let file = pendingFile {
                VStack(alignment: .leading, spacing: 0) {
                    HStack(spacing: 12) {
                        if file.isImage, let image = UIImage(contentsOfFile: file.url.path()) {
                            Image(uiImage: image).resizable().scaledToFill().frame(width: 44, height: 44).clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
                        } else {
                            Image(systemName: file.isAudio ? "mic" : "doc.badge.plus").font(.system(size: 24)).foregroundStyle(accent.color).frame(width: 44)
                        }
                        VStack(alignment: .leading, spacing: 2) {
                            Text(file.isAudio ? c.audioReady : file.name).font(.subheadline.weight(.semibold)).foregroundStyle(accent.palette.ink).lineLimit(1)
                            Text(c.attached).font(.caption).foregroundStyle(accent.palette.muted)
                        }
                        Spacer()
                        Button { pendingFile = nil } label: { Image(systemName: "xmark.circle.fill").font(.system(size: 22)).foregroundStyle(accent.palette.muted) }
                            .disabled(busy).accessibilityLabel(c.removeFile)
                    }
                    .padding(12)
                    if file.isAudio { LocalAudioPreview(url: file.url).padding(.horizontal, 14).padding(.bottom, 12) }
                    if !fileAllowed { Text(c.unsupportedAttachment).font(.caption).foregroundStyle(accent.palette.danger).padding(.horizontal, 14).padding(.bottom, 8) }
                }
                .overlay(alignment: .bottom) { Rectangle().fill(accent.palette.line).frame(height: 0.5) }
            }
            if recorder.state != .idle {
                recordingBar
            } else {
                HStack(alignment: .bottom, spacing: 4) {
                    Button { attachMenu = true } label: {
                        Image(systemName: "plus").font(.system(size: 24)).foregroundStyle(accent.palette.muted).frame(width: 38, height: 38)
                    }
                    .disabled(busy || (!canAttach && !(onSavedReplies != nil && textAllowed)))
                    .accessibilityLabel(s.attach)
                    .confirmationDialog(s.sheetTitle, isPresented: $attachMenu, titleVisibility: .visible) {
                        if let onSavedReplies, textAllowed { Button(c.canned, action: onSavedReplies) }
                        if mediaAllowed {
                            Button(s.fromLibrary) { showPhotos = true }
                            Button(s.fromCamera) { showCamera = true }
                        }
                        if canAttach { Button(c.file) { showFiles = true } }
                        Button(s.cancel, role: .cancel) {}
                    }
                    Button { Task { await startRecording() } } label: {
                        Image(systemName: "mic").font(.system(size: 20)).foregroundStyle(accent.palette.muted).frame(width: 44, height: 44)
                    }
                    .disabled(busy || capabilities.audio != true || pendingFile != nil)
                    .opacity(pendingFile != nil ? 0.5 : 1)
                    .accessibilityLabel(c.recordAudio)
                    TextField(pendingFile != nil ? c.caption : s.placeholder, text: $draft, axis: .vertical)
                        .lineLimit(1...5)
                        .focused($focused)
                        .disabled(busy || !textAllowed)
                        .foregroundStyle(accent.palette.ink)
                        .padding(.horizontal, 15)
                        .padding(.vertical, 9)
                        .background(accent.palette.canvas, in: RoundedRectangle(cornerRadius: 19, style: .continuous))
                        .overlay(RoundedRectangle(cornerRadius: 19, style: .continuous).strokeBorder(accent.palette.line, lineWidth: 0.5))
                        .accessibilityLabel(pendingFile != nil ? c.caption : s.placeholder)
                    if canSend {
                        Button { Task { await send() } } label: {
                            ZStack {
                                Circle().fill(accent.color).frame(width: 38, height: 38)
                                if busy { ProgressView().tint(accent.onColor).controlSize(.small) }
                                else { Image(systemName: "arrow.up").font(.system(size: 18, weight: .semibold)).foregroundStyle(accent.onColor) }
                            }
                        }
                        .disabled(busy)
                        .accessibilityLabel(pendingFile?.isAudio == true ? s.sendVoice : s.send)
                    }
                }
                .padding(.horizontal, 8)
                .padding(.vertical, 8)
            }
        }
        .photosPicker(isPresented: $showPhotos, selection: $photoItem, matching: mediaFilter, photoLibrary: .shared())
        .onChange(of: photoItem) { _, item in
            guard let item else { return }
            Task { await importPhoto(item); photoItem = nil }
        }
        .fullScreenCover(isPresented: $showCamera) {
            CameraPicker(allowsVideo: capabilities.video == true) { file in
                if let file { stage(file) }
            }
            .ignoresSafeArea()
        }
        .fileImporter(isPresented: $showFiles, allowedContentTypes: importTypes) { result in
            switch result {
            case .success(let url): importFile(url)
            case .failure: onError(c.pickFailed)
            }
        }
        .onAppear {
            guard !loaded else { return }
            loaded = true
            let saved = ComposerDrafts.shared.get(draftKey)
            draft = saved?.text ?? ""
            pendingFile = saved?.file
        }
        .onChange(of: draft) { _, value in
            // Typing "/" in an empty field opens the saved replies, as the web does.
            if value == "/", let onSavedReplies, textAllowed {
                draft = ""
                onSavedReplies()
                return
            }
            saveDraft()
        }
        .onChange(of: pendingFile) { _, file in
            saveDraft()
            if file != nil { onAttachmentSelected?() }
        }
        .onChange(of: insertedReply) { _, text in
            guard let text else { return }
            draft = text
            focused = true
            insertedReply = nil
        }
        .onChange(of: scenePhase) { _, phase in
            // Preserve a running or paused note on any interruption, never auto-send it.
            if phase == .background, let file = recorder.interrupt() { pendingFile = file }
        }
        .alert(item: $alert) { Alert(title: Text($0.title), message: $0.message.map(Text.init)) }
    }

    private var recordingBar: some View {
        let s = Strings.current.composer
        let c = ChatStrings.current
        let paused = recorder.state == .paused
        return HStack(spacing: 8) {
            Button { _ = try? recorder.stop(keep: false) } label: {
                Image(systemName: "trash").font(.system(size: 20)).foregroundStyle(accent.palette.danger).frame(width: 38, height: 38)
            }
            .disabled(recorder.state == .stopping)
            .accessibilityLabel(s.discardLabel)
            Circle().fill(accent.palette.danger).frame(width: 9, height: 9).opacity(paused ? 0.3 : 1)
                .modifier(Blink(active: recorder.state == .recording))
            Text(recorder.state == .preparing ? s.recording : AudioPlayerModel.clock(recorder.elapsed))
                .font(.subheadline.monospacedDigit()).foregroundStyle(accent.palette.ink).frame(minWidth: 42, alignment: .leading)
            HStack(spacing: 2) {
                ForEach(Array(recorder.levels.enumerated()), id: \.offset) { _, level in
                    RoundedRectangle(cornerRadius: 1.5).fill(paused ? accent.palette.subtle : accent.color).frame(height: 4 + level * 22)
                }
            }
            .frame(maxWidth: .infinity, minHeight: 26)
            Button { paused ? recorder.resume() : recorder.pause() } label: {
                Image(systemName: paused ? "play.fill" : "pause.fill").font(.system(size: 18)).foregroundStyle(accent.palette.muted).frame(width: 38, height: 38)
            }
            .disabled(recorder.state == .preparing || recorder.state == .stopping)
            .accessibilityLabel(paused ? s.resume : s.pause)
            Button { finishRecording() } label: {
                HStack(spacing: 5) { Image(systemName: "stop.fill").font(.system(size: 14)); Text(c.review).font(.caption.weight(.bold)) }
                    .foregroundStyle(accent.onColor).padding(.horizontal, 12).frame(minHeight: 40).background(accent.color, in: Capsule())
            }
            .disabled(recorder.state == .preparing || recorder.state == .stopping)
            .accessibilityLabel(c.reviewAudio)
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 8)
    }

    private var mediaFilter: PHPickerFilter {
        switch (capabilities.image == true, capabilities.video == true) {
        case (true, true): return .any(of: [.images, .videos])
        case (false, true): return .videos
        default: return .images
        }
    }

    private var importTypes: [UTType] {
        if capabilities.file == true, channel != "instagram" { return [.item] }
        var types: [UTType] = []
        if capabilities.image == true { types.append(.image) }
        if capabilities.video == true { types.append(.movie) }
        if capabilities.audio == true { types.append(.audio) }
        if capabilities.file == true { types.append(.pdf) }
        return types.isEmpty ? [.item] : types
    }

    private func saveDraft() {
        guard loaded else { return }
        ComposerDrafts.shared.set(draftKey, ComposerDrafts.Draft(text: draft, file: pendingFile))
    }

    private func stage(_ file: OutgoingFile) {
        guard InboxRules.acceptsAttachment(channel: channel, capabilities: capabilities, mime: file.mime) else {
            onError(ChatStrings.current.unsupportedAttachment)
            return
        }
        pendingFile = file
    }

    private func importPhoto(_ item: PhotosPickerItem) async {
        let c = ChatStrings.current
        do {
            guard let data = try await item.loadTransferable(type: Data.self) else { return }
            let type = item.supportedContentTypes.first
            let isVideo = type?.conforms(to: .movie) ?? false
            let ext = type?.preferredFilenameExtension ?? (isVideo ? "mp4" : "jpg")
            let mime = type?.preferredMIMEType ?? (isVideo ? "video/\(ext)" : (MimeTypes.images[ext] ?? "image/jpeg"))
            let name = "\(isVideo ? "video" : "photo").\(ext)"
            let url = AttachmentCache.stagingURL(name: name)
            try data.write(to: url, options: .atomic)
            stage(OutgoingFile(url: url, name: name, mime: mime))
        } catch {
            onError(c.pickFailed)
        }
    }

    private func importFile(_ source: URL) {
        let c = ChatStrings.current
        let access = source.startAccessingSecurityScopedResource()
        defer { if access { source.stopAccessingSecurityScopedResource() } }
        do {
            let name = source.lastPathComponent
            let target = AttachmentCache.stagingURL(name: name)
            try FileManager.default.copyItem(at: source, to: target)
            let mime = UTType(filenameExtension: source.pathExtension)?.preferredMIMEType ?? "application/octet-stream"
            stage(OutgoingFile(url: target, name: name, mime: mime))
        } catch {
            onError(c.pickFailed)
        }
    }

    private func startRecording() async {
        let s = Strings.current.composer
        let c = ChatStrings.current
        guard !busy, capabilities.audio == true else { return }
        do { try await recorder.start() }
        catch is Recorder.Denied { alert = AppModel.AlertContent(title: s.micDeniedTitle, message: s.micDeniedBody) }
        catch is Recorder.Unavailable { alert = AppModel.AlertContent(title: s.recordFailedTitle, message: c.micUnavailable) }
        catch { alert = AppModel.AlertContent(title: s.recordFailedTitle, message: s.recordFailedBody) }
    }

    private func finishRecording() {
        let c = ChatStrings.current
        do {
            if let file = try recorder.stop(keep: true) { pendingFile = file }
        } catch is Recorder.TooShort { onError(c.recordingTooShort) }
        catch { onError(c.recordFailed) }
    }

    private func send() async {
        guard canSend, !busy, !sending else { return }
        sending = true
        defer { sending = false }
        let text = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        let submittedText = draft
        let submittedFile = pendingFile
        let epoch = ComposerDrafts.shared.epoch
        let sent = if let file = pendingFile { await onSendFile(file, text) } else { await onSendText(text) }
        guard sent else { return }
        // API success can arrive after navigation left this composer. Clear the
        // matching saved draft without erasing a newer one.
        let current = ComposerDrafts.shared.get(draftKey)
        if epoch == ComposerDrafts.shared.epoch, current?.text == submittedText, current?.file?.url == submittedFile?.url {
            ComposerDrafts.shared.remove(draftKey)
        }
        if draft == submittedText { draft = "" }
        if pendingFile?.url == submittedFile?.url {
            pendingFile = nil
            if let url = submittedFile?.url { try? FileManager.default.removeItem(at: url) }
        }
    }
}

/// The recording dot pulses while the microphone is open.
private struct Blink: ViewModifier {
    let active: Bool
    @State private var dim = false
    func body(content: Content) -> some View {
        content
            .opacity(active && dim ? 0.25 : 1)
            .animation(active ? .easeInOut(duration: 0.6).repeatForever(autoreverses: true) : .default, value: dim)
            .onAppear { dim = active }
            .onChange(of: active) { _, value in dim = value }
    }
}

/// The system camera, for a photo or a short video to send.
struct CameraPicker: UIViewControllerRepresentable {
    let allowsVideo: Bool
    let completion: (OutgoingFile?) -> Void

    func makeUIViewController(context: Context) -> UIImagePickerController {
        let picker = UIImagePickerController()
        picker.sourceType = UIImagePickerController.isSourceTypeAvailable(.camera) ? .camera : .photoLibrary
        picker.mediaTypes = allowsVideo ? [UTType.image.identifier, UTType.movie.identifier] : [UTType.image.identifier]
        picker.delegate = context.coordinator
        return picker
    }

    func updateUIViewController(_ controller: UIImagePickerController, context: Context) {}
    func makeCoordinator() -> Coordinator { Coordinator(completion: completion) }

    final class Coordinator: NSObject, UIImagePickerControllerDelegate, UINavigationControllerDelegate {
        let completion: (OutgoingFile?) -> Void
        init(completion: @escaping (OutgoingFile?) -> Void) { self.completion = completion }

        func imagePickerControllerDidCancel(_ picker: UIImagePickerController) {
            picker.dismiss(animated: true) { self.completion(nil) }
        }

        func imagePickerController(_ picker: UIImagePickerController, didFinishPickingMediaWithInfo info: [UIImagePickerController.InfoKey: Any]) {
            var file: OutgoingFile?
            if let movie = info[.mediaURL] as? URL {
                let target = AttachmentCache.stagingURL(name: "video.\(movie.pathExtension.isEmpty ? "mov" : movie.pathExtension)")
                if (try? FileManager.default.copyItem(at: movie, to: target)) != nil {
                    file = OutgoingFile(url: target, name: target.lastPathComponent.components(separatedBy: "-").last ?? "video.mov", mime: UTType(filenameExtension: target.pathExtension)?.preferredMIMEType ?? "video/quicktime")
                }
            } else if let image = info[.originalImage] as? UIImage, let data = image.jpegData(compressionQuality: 0.8) {
                let target = AttachmentCache.stagingURL(name: "photo.jpg")
                if (try? data.write(to: target, options: .atomic)) != nil { file = OutgoingFile(url: target, name: "photo.jpg", mime: "image/jpeg") }
            }
            picker.dismiss(animated: true) { self.completion(file) }
        }
    }
}
