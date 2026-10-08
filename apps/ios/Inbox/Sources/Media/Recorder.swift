import AVFoundation
import Foundation
import Observation

/// A voice note in progress: level meter, elapsed time, pause and resume.
///
/// Transitions are serialized through this object so a system foreground event
/// can never resume a microphone the person paused.
@MainActor
@Observable
final class Recorder {
    enum State { case idle, preparing, recording, paused, stopping }

    struct Unavailable: Error {}
    struct Denied: Error {}
    struct TooShort: Error {}

    private(set) var state: State = .idle
    private(set) var levels: [Double] = Array(repeating: 0.08, count: Recorder.bars)
    private(set) var elapsed: TimeInterval = 0

    static let bars = 26
    private static let meterInterval: TimeInterval = 0.09

    private var recorder: AVAudioRecorder?
    private var meter: Timer?
    private var fileURL: URL?
    private var accumulated: TimeInterval = 0
    private var segmentStart: Date?

    var isActive: Bool { state == .recording || state == .paused }

    /// Turn the recorder's decibel reading into a 0..1 height.
    private static func level(from decibels: Float) -> Double {
        guard decibels.isFinite else { return 0.08 }
        // Metering is dBFS: 0 is as loud as it gets, -60 is effectively silence.
        let normalised = (Double(max(-60, min(0, decibels))) + 60) / 60
        return max(0.08, pow(normalised, 1.6))
    }

    func start() async throws {
        guard state == .idle else { return }
        state = .preparing
        do {
            let granted = await AVAudioApplication.requestRecordPermission()
            guard state == .preparing else { return }
            guard granted else { throw Denied() }
            try AudioSessionMode.prepareRecording()
            let url = AttachmentCache.stagingURL(name: "voice-note.m4a")
            let settings: [String: Any] = [
                AVFormatIDKey: Int(kAudioFormatMPEG4AAC),
                AVSampleRateKey: 44100,
                AVNumberOfChannelsKey: 1,
                AVEncoderAudioQualityKey: AVAudioQuality.high.rawValue,
            ]
            let recorder = try AVAudioRecorder(url: url, settings: settings)
            recorder.isMeteringEnabled = true
            guard recorder.prepareToRecord(), recorder.record() else { throw Unavailable() }
            guard state == .preparing else { recorder.stop(); try? FileManager.default.removeItem(at: url); return }
            self.recorder = recorder
            fileURL = url
            accumulated = 0
            elapsed = 0
            segmentStart = Date()
            levels = Array(repeating: 0.08, count: Recorder.bars)
            state = .recording
            startMeter()
        } catch {
            state = .idle
            AudioSessionMode.release()
            throw error
        }
    }

    private func startMeter() {
        meter?.invalidate()
        // Driven by the clock rather than by the reading changing: silence
        // reports the same number every time, and a meter that freezes while
        // someone is still recording looks like a hang.
        meter = Timer.scheduledTimer(withTimeInterval: Recorder.meterInterval, repeats: true) { [weak self] _ in
            Task { @MainActor in self?.tick() }
        }
    }

    private func tick() {
        guard let recorder, state == .recording else { return }
        recorder.updateMeters()
        levels.removeFirst()
        levels.append(Recorder.level(from: recorder.averagePower(forChannel: 0)))
        if let segmentStart { elapsed = accumulated + Date().timeIntervalSince(segmentStart) }
    }

    func pause() {
        guard state == .recording, let recorder else { return }
        recorder.pause()
        if let segmentStart { accumulated += Date().timeIntervalSince(segmentStart) }
        segmentStart = nil
        elapsed = accumulated
        state = .paused
    }

    func resume() {
        guard state == .paused, let recorder else { return }
        guard recorder.record() else { return }
        segmentStart = Date()
        state = .recording
    }

    /// Ends the note. `keep` returns the file; otherwise it is deleted.
    func stop(keep: Bool) throws -> OutgoingFile? {
        if state == .preparing {
            state = .idle
            return nil
        }
        guard isActive, let recorder, let url = fileURL else { return nil }
        state = .stopping
        meter?.invalidate()
        meter = nil
        if let segmentStart { accumulated += Date().timeIntervalSince(segmentStart) }
        segmentStart = nil
        recorder.stop()
        self.recorder = nil
        fileURL = nil
        AudioSessionMode.release()
        defer { state = .idle; elapsed = 0 }
        guard keep else {
            try? FileManager.default.removeItem(at: url)
            return nil
        }
        guard accumulated >= 0.3 else {
            try? FileManager.default.removeItem(at: url)
            throw TooShort()
        }
        return OutgoingFile(url: url, name: "voice-note.m4a", mime: "audio/mp4")
    }

    /// The app left the foreground: keep what was recorded, never auto-send it.
    func interrupt() -> OutgoingFile? {
        guard isActive else {
            if state == .preparing { state = .idle }
            return nil
        }
        return try? stop(keep: true)
    }
}
