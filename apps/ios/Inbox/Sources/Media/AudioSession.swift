import AVFoundation

/// One place that touches AVAudioSession, so playback and recording never
/// configure it against each other.
enum AudioSessionMode {
    static func preparePlayback() throws {
        let session = AVAudioSession.sharedInstance()
        // Plays in silent mode, like every messaging app's voice notes.
        try session.setCategory(.playback, mode: .default, options: [])
        try session.setActive(true)
    }

    static func prepareRecording() throws {
        let session = AVAudioSession.sharedInstance()
        try session.setCategory(.playAndRecord, mode: .default, options: [.defaultToSpeaker, .allowBluetooth])
        try session.setActive(true)
    }

    static func release() {
        try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
    }
}
