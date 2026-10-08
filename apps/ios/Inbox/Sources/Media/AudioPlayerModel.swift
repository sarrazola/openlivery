import AVFoundation
import Foundation
import Observation

/// Playback of one voice note from a local file.
@MainActor
@Observable
final class AudioPlayerModel: NSObject, AVAudioPlayerDelegate {
    private(set) var isPlaying = false
    private(set) var duration: TimeInterval = 0
    private(set) var elapsed: TimeInterval = 0
    private(set) var failed = false

    private var player: AVAudioPlayer?
    private var timer: Timer?

    var progress: Double { duration > 0 ? min(elapsed / duration, 1) : 0 }

    func load(_ url: URL) {
        stopTimer()
        player?.stop()
        failed = false
        isPlaying = false
        elapsed = 0
        do {
            let player = try AVAudioPlayer(contentsOf: url)
            player.delegate = self
            player.prepareToPlay()
            self.player = player
            duration = player.duration
        } catch {
            player = nil
            duration = 0
            failed = true
        }
    }

    func toggle() {
        guard let player else { failed = true; return }
        if player.isPlaying {
            player.pause()
            isPlaying = false
            stopTimer()
            return
        }
        do { try AudioSessionMode.preparePlayback() } catch { failed = true; return }
        // Replaying after it ended needs an explicit rewind.
        if duration > 0, player.currentTime >= duration - 0.15 { player.currentTime = 0 }
        guard player.play() else { failed = true; return }
        isPlaying = true
        timer = Timer.scheduledTimer(withTimeInterval: 0.2, repeats: true) { [weak self] _ in
            Task { @MainActor in
                guard let self, let player = self.player else { return }
                self.elapsed = player.currentTime
            }
        }
    }

    private func stopTimer() {
        timer?.invalidate()
        timer = nil
    }

    nonisolated func audioPlayerDidFinishPlaying(_ player: AVAudioPlayer, successfully flag: Bool) {
        Task { @MainActor in
            self.isPlaying = false
            self.elapsed = self.duration
            self.stopTimer()
        }
    }

    nonisolated func audioPlayerDecodeErrorDidOccur(_ player: AVAudioPlayer, error: Error?) {
        Task { @MainActor in
            self.failed = true
            self.isPlaying = false
            self.stopTimer()
        }
    }

    static func clock(_ seconds: TimeInterval) -> String {
        guard seconds.isFinite, seconds >= 0 else { return "0:00" }
        let total = Int(seconds)
        return String(format: "%d:%02d", total / 60, total % 60)
    }
}
