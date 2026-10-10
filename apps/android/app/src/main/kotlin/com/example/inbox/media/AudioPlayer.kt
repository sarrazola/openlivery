package com.example.inbox.media

import android.media.MediaPlayer
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import java.io.File

/** One voice note at a time plays; starting another stops the first. */
object AudioPlayer {
    var playingPath by mutableStateOf<String?>(null); private set
    var progress by mutableFloatStateOf(0f); private set
    var durationMs by mutableStateOf(0); private set

    private var player: MediaPlayer? = null

    fun toggle(file: File) {
        if (playingPath == file.path) {
            player?.let { if (it.isPlaying) it.pause() else it.start() }
            return
        }
        stop()
        val next = MediaPlayer()
        try {
            next.setDataSource(file.path)
            next.prepare()
            next.setOnCompletionListener { progress = 1f; stop() }
            next.start()
            player = next; playingPath = file.path; durationMs = next.duration; progress = 0f
        } catch (error: Exception) {
            next.release()
        }
    }

    val isPlaying: Boolean get() = player?.isPlaying == true

    /** Called on a timer while a voice note is on screen. */
    fun tick() {
        val current = player ?: return
        if (durationMs > 0) progress = (current.currentPosition.toFloat() / durationMs).coerceIn(0f, 1f)
    }

    fun stop() {
        player?.let { runCatching { it.stop() }; it.release() }
        player = null
        playingPath = null
    }

    fun duration(file: File): Int = runCatching {
        MediaPlayer().let { p -> p.setDataSource(file.path); p.prepare(); val d = p.duration; p.release(); d }
    }.getOrDefault(0)
}
