import QuickLook
import SwiftUI

/// Rendering what came in with a message.
///
/// Attachments live behind the portal session, so none of them can be a plain
/// URL in an image view: every fetch carries the bearer token. Images render
/// inline, voice notes get a play button and a track, and anything else falls
/// back to a row you can tap to open.
struct AttachmentView: View {
    let attachment: Attachment
    let server: String
    let session: Session
    let conversationId: String
    let outgoing: Bool
    @Environment(\.accent) private var accent

    var body: some View {
        // An outgoing bubble is painted the brand colour and an incoming one is
        // not, so a control needs a fill that stands off whichever it sits on and
        // a glyph that stands off the fill.
        let control: Color = outgoing ? accent.onColor : accent.palette.ink
        let onControl: Color = outgoing ? accent.color : accent.palette.surface
        if let url = PortalAPI.attachmentURL(server, session, conversationId: conversationId, attachmentId: attachment.id) {
            switch attachment.kind {
            case "image": ImageAttachment(url: url, token: session.token, id: attachment.id)
            case "audio": AudioAttachment(url: url, token: session.token, id: attachment.id, mime: attachment.mime, control: control, onControl: onControl)
            default: FileAttachment(url: url, token: session.token, attachment: attachment, control: control)
            }
        }
    }
}

/// An image fetched with the session's credentials, tappable to view full size.
struct ImageAttachment: View {
    let url: URL
    let token: String
    let id: String
    @Environment(\.accent) private var accent
    @State private var image: UIImage?
    @State private var failed = false
    @State private var expanded = false
    @State private var attempt = 0

    var body: some View {
        let c = ChatStrings.current
        Group {
            if let image {
                Button { expanded = true } label: {
                    Image(uiImage: image).resizable().scaledToFill().frame(width: 230, height: 230).clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
                }
                .buttonStyle(.plain)
                .accessibilityLabel(c.viewImage)
            } else if failed {
                Button { attempt += 1 } label: {
                    VStack(spacing: 8) {
                        Text(Strings.current.attachment.imageUnavailable).font(.footnote).foregroundStyle(accent.palette.muted)
                        Text(c.retry).foregroundStyle(accent.palette.ink)
                    }
                    .frame(width: 230, height: 120)
                    .background(accent.palette.bubbleIn, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                }
                .buttonStyle(.plain)
                .accessibilityLabel(c.attachmentRetry)
            } else {
                ProgressView().frame(width: 230, height: 230)
            }
        }
        .task(id: attempt) {
            failed = false
            do {
                let local = try await AttachmentCache.download(url, token: token, id: id, extension: "img", force: attempt > 0)
                image = UIImage(contentsOfFile: local.path())
                if image == nil { failed = true }
            } catch { failed = true }
        }
        .fullScreenCover(isPresented: $expanded) {
            ZStack(alignment: .topTrailing) {
                accent.palette.surface.ignoresSafeArea()
                if let image {
                    ScrollView([.horizontal, .vertical]) {
                        Image(uiImage: image).resizable().scaledToFit().containerRelativeFrame([.horizontal, .vertical])
                    }
                }
                Button { expanded = false } label: { Image(systemName: "xmark").font(.title2).foregroundStyle(accent.palette.ink).padding(18) }
                    .accessibilityLabel(c.close)
            }
        }
    }
}

/// The voice-note layout, shared by the loading and playable states.
struct VoiceNoteRow: View {
    let control: Color
    let onControl: Color
    let busy: Bool
    let playing: Bool
    let progress: Double
    let label: String
    var accessibilityLabel: String? = nil
    var action: (() -> Void)? = nil

    var body: some View {
        HStack(spacing: 10) {
            Button { action?() } label: {
                ZStack {
                    Circle().fill(control).frame(width: 36, height: 36)
                    if busy { ProgressView().tint(onControl).controlSize(.small) }
                    else { Image(systemName: playing ? "pause.fill" : "play.fill").font(.system(size: 14)).foregroundStyle(onControl) }
                }
            }
            .buttonStyle(.plain)
            .disabled(action == nil)
            .accessibilityLabel(accessibilityLabel ?? "")
            VStack(alignment: .leading, spacing: 7) {
                GeometryReader { geometry in
                    ZStack(alignment: .leading) {
                        Capsule().fill(control.opacity(0.3)).frame(height: 3)
                        Capsule().fill(control).frame(width: geometry.size.width * progress, height: 3)
                    }
                }
                .frame(height: 3)
                Text(label).font(.caption).foregroundStyle(control.opacity(0.85))
            }
        }
        .frame(minWidth: 200)
        .padding(.vertical, 2)
    }
}

/// Downloads a voice note once, then plays it from disk.
struct AudioAttachment: View {
    let url: URL
    let token: String
    let id: String
    let mime: String
    let control: Color
    let onControl: Color
    @State private var player = AudioPlayerModel()
    @State private var local: URL?
    @State private var failed = false
    @State private var attempt = 0

    var body: some View {
        let c = ChatStrings.current
        let s = Strings.current.attachment
        Group {
            if failed || player.failed {
                Button { attempt += 1 } label: {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(c.audioFailed).foregroundStyle(control)
                        Text(c.retry).fontWeight(.semibold).foregroundStyle(control)
                    }
                    .padding(10)
                }
                .buttonStyle(.plain)
                .accessibilityLabel(c.attachmentRetry)
            } else if local == nil {
                VoiceNoteRow(control: control, onControl: onControl, busy: true, playing: false, progress: 0, label: "0:00")
            } else {
                VoiceNoteRow(
                    control: control, onControl: onControl, busy: false, playing: player.isPlaying, progress: player.progress,
                    label: AudioPlayerModel.clock(player.isPlaying || player.elapsed > 0 ? player.elapsed : player.duration),
                    accessibilityLabel: player.isPlaying ? s.pause : s.play
                ) { player.toggle() }
            }
        }
        .task(id: attempt) {
            failed = false
            local = nil
            let base = mime.lowercased().split(separator: ";").first.map(String.init)?.trimmingCharacters(in: .whitespaces) ?? ""
            let convert = !MimeTypes.nativeAudio.contains(base)
            let ext = convert ? "m4a" : MimeTypes.audioExtension(mime)
            let playback = convert ? url.appending(queryItems: [URLQueryItem(name: "format", value: "m4a")]) : url
            do {
                let file = try await AttachmentCache.download(playback, token: token, id: id, extension: ext, force: attempt > 0)
                player.load(file)
                local = file
            } catch { failed = true }
        }
    }
}

/// Anything that is not an image or a voice note: tap to download and preview.
struct FileAttachment: View {
    let url: URL
    let token: String
    let attachment: Attachment
    let control: Color
    @State private var opening = false
    @State private var preview: URL?
    @State private var failure: AppModel.AlertContent?

    var body: some View {
        let c = ChatStrings.current
        let s = Strings.current.attachment
        Button {
            guard !opening else { return }
            opening = true
            Task {
                defer { opening = false }
                do {
                    let ext = MimeTypes.extensionFor(filename: attachment.filename, fallback: attachment.kind == "video" ? "mp4" : "bin")
                    preview = try await AttachmentCache.download(url, token: token, id: attachment.id, extension: ext)
                } catch {
                    failure = AppModel.AlertContent(title: c.attachmentFailed, message: error.localizedDescription)
                }
            }
        } label: {
            HStack(spacing: 10) {
                ZStack {
                    RoundedRectangle(cornerRadius: 8, style: .continuous).strokeBorder(control, lineWidth: 1).frame(width: 32, height: 32)
                    if opening { ProgressView().tint(control).controlSize(.small) }
                    else { Image(systemName: attachment.kind == "video" ? "play.fill" : "arrow.down.circle").font(.system(size: 14)).foregroundStyle(control) }
                }
                .opacity(0.8)
                VStack(alignment: .leading, spacing: 1) {
                    Text(attachment.filename ?? s.generic).font(.subheadline.weight(.semibold)).foregroundStyle(control).lineLimit(1)
                    if attachment.sizeBytes > 0 { Text(MimeTypes.humanSize(attachment.sizeBytes)).font(.caption2).foregroundStyle(control.opacity(0.7)) }
                }
            }
            .frame(minWidth: 180, alignment: .leading)
            .padding(.vertical, 2)
        }
        .buttonStyle(.plain)
        .disabled(opening)
        .accessibilityLabel("\(c.openFile): \(attachment.filename ?? s.generic)")
        .quickLookPreview($preview)
        .alert(item: $failure) { Alert(title: Text($0.title), message: $0.message.map(Text.init)) }
    }
}

/// Playback of a note that was just recorded, before it is sent.
struct LocalAudioPreview: View {
    let url: URL
    @Environment(\.accent) private var accent
    @State private var player = AudioPlayerModel()

    var body: some View {
        let s = Strings.current.attachment
        VoiceNoteRow(
            control: accent.color, onControl: accent.onColor, busy: false, playing: player.isPlaying, progress: player.progress,
            label: AudioPlayerModel.clock(player.isPlaying || player.elapsed > 0 ? player.elapsed : player.duration),
            accessibilityLabel: player.isPlaying ? s.pause : s.play
        ) { player.toggle() }
        .task(id: url) { player.load(url) }
    }
}
