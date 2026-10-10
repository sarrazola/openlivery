package com.example.inbox.media

import android.content.Context
import android.media.MediaRecorder
import android.os.Build
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import com.example.inbox.api.OutgoingFile
import java.io.File

/** A voice note: AAC in an MPEG-4 container, the way the other clients send it. */
class Recorder(private val context: Context) {
    enum class State { IDLE, RECORDING, PAUSED }

    var state by mutableStateOf(State.IDLE); private set
    var elapsedMs by mutableLongStateOf(0L); private set
    var level by mutableStateOf(0f); private set

    private var recorder: MediaRecorder? = null
    private var file: File? = null
    private var startedAt = 0L
    private var accumulated = 0L

    fun start(): Boolean {
        if (state != State.IDLE) return false
        val target = AttachmentCache.stagingFile("voice-note.m4a")
        val next = if (Build.VERSION.SDK_INT >= 31) MediaRecorder(context) else @Suppress("DEPRECATION") MediaRecorder()
        return try {
            next.setAudioSource(MediaRecorder.AudioSource.MIC)
            next.setOutputFormat(MediaRecorder.OutputFormat.MPEG_4)
            next.setAudioEncoder(MediaRecorder.AudioEncoder.AAC)
            next.setAudioEncodingBitRate(64_000)
            next.setAudioSamplingRate(44_100)
            next.setOutputFile(target.path)
            next.prepare()
            next.start()
            recorder = next; file = target; accumulated = 0; startedAt = System.currentTimeMillis(); elapsedMs = 0
            state = State.RECORDING
            true
        } catch (error: Exception) {
            next.release(); target.delete(); false
        }
    }

    /** Called on a timer by the composer while a recording is on screen. */
    fun tick() {
        if (state == State.RECORDING) {
            elapsedMs = accumulated + (System.currentTimeMillis() - startedAt)
            level = runCatching { (recorder?.maxAmplitude ?: 0) / 32767f }.getOrDefault(0f)
        }
    }

    fun pause() {
        if (state != State.RECORDING) return
        runCatching { recorder?.pause() }
        accumulated += System.currentTimeMillis() - startedAt
        state = State.PAUSED
    }

    fun resume() {
        if (state != State.PAUSED) return
        runCatching { recorder?.resume() }
        startedAt = System.currentTimeMillis()
        state = State.RECORDING
    }

    /** Ends the recording; the file is handed back only when it is kept and long enough to mean something. */
    fun stop(keep: Boolean): OutgoingFile? {
        val current = recorder ?: return null
        if (state == State.RECORDING) accumulated += System.currentTimeMillis() - startedAt
        runCatching { current.stop() }
        current.release()
        recorder = null
        state = State.IDLE
        val target = file
        file = null
        val tooShort = accumulated < 700
        if (!keep || target == null || tooShort || target.length() == 0L) { target?.delete(); return null }
        return OutgoingFile(target, "voice-note.m4a", "audio/mp4")
    }

    companion object {
        fun clock(ms: Long): String {
            val total = (ms / 1000).coerceAtLeast(0)
            return String.format(java.util.Locale.ROOT, "%d:%02d", total / 60, total % 60)
        }
    }
}
