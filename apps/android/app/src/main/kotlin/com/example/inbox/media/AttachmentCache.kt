package com.example.inbox.media

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.util.LruCache
import com.example.inbox.api.ApiClient
import java.io.File
import java.security.MessageDigest
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/**
 * Attachments and logos, fetched once and kept on disk under the app's cache
 * directory, which the system may clear when space runs low. Decoded images
 * also sit in a small memory cache so a list scrolls without re-decoding.
 */
object AttachmentCache {
    private lateinit var directory: File
    private lateinit var staging: File
    private val bitmaps = object : LruCache<String, Bitmap>(24 * 1024 * 1024) {
        override fun sizeOf(key: String, value: Bitmap) = value.byteCount
    }

    fun install(context: Context) {
        directory = File(context.cacheDir, "attachments").also { it.mkdirs() }
        staging = File(context.cacheDir, "outgoing").also { it.mkdirs() }
    }

    private fun hash(text: String): String = MessageDigest.getInstance("SHA-256").digest(text.toByteArray()).take(12).joinToString("") { "%02x".format(it) }

    fun localFile(remote: String, extension: String): File = File(directory, "${hash(remote)}.$extension")

    /** The local copy, downloading it with the session's credential when it is not there yet. */
    suspend fun download(remote: String, token: String?, extension: String, force: Boolean = false): File = withContext(Dispatchers.IO) {
        val target = localFile(remote, extension)
        if (!force && target.exists() && target.length() > 0) return@withContext target
        val bytes = ApiClient.bytes(remote, token)
        val temporary = File(directory, "${target.name}.part")
        temporary.writeBytes(bytes)
        if (!temporary.renameTo(target)) { target.delete(); temporary.renameTo(target) }
        target
    }

    /** A decoded image bounded to a reasonable size, from memory or disk. */
    suspend fun bitmap(remote: String, token: String?, force: Boolean = false, maxSide: Int = 1600): Bitmap? {
        if (!force) bitmaps.get(remote)?.let { return it }
        val file = download(remote, token, "img", force)
        val decoded = withContext(Dispatchers.IO) {
            val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
            BitmapFactory.decodeFile(file.path, bounds)
            var sample = 1
            while (bounds.outWidth / sample > maxSide || bounds.outHeight / sample > maxSide) sample *= 2
            BitmapFactory.decodeFile(file.path, BitmapFactory.Options().apply { inSampleSize = sample })
        } ?: return null
        bitmaps.put(remote, decoded)
        return decoded
    }

    /** Where an outgoing file is staged before it is uploaded. */
    fun stagingFile(name: String): File = File(staging, "${System.currentTimeMillis()}-$name")

    fun clearStaging() { staging.listFiles()?.forEach { it.delete() } }
}

object MimeTypes {
    val images = mapOf("jpg" to "image/jpeg", "jpeg" to "image/jpeg", "png" to "image/png", "webp" to "image/webp", "heic" to "image/heic", "gif" to "image/gif")

    fun extensionFor(filename: String?, fallback: String): String {
        val match = filename?.let { Regex("\\.([a-zA-Z0-9]{1,8})$").find(it) } ?: return fallback
        return match.groupValues[1].lowercase()
    }

    /** Native playback handles these; anything else is asked from the server as m4a. */
    val nativeAudio = setOf("audio/mp4", "audio/m4a", "audio/x-m4a", "audio/mpeg", "audio/mp3", "audio/wav", "audio/x-wav", "audio/aac", "audio/ogg", "audio/opus")

    fun audioExtension(mime: String): String = when (mime.lowercase().substringBefore(";").trim()) {
        "audio/mpeg", "audio/mp3" -> "mp3"
        "audio/wav", "audio/x-wav" -> "wav"
        "audio/ogg", "audio/opus" -> "ogg"
        "audio/aac" -> "aac"
        else -> "m4a"
    }

    fun humanSize(bytes: Long): String = when {
        bytes < 1024 -> "$bytes B"
        bytes < 1024 * 1024 -> "${bytes / 1024} KB"
        else -> String.format(java.util.Locale.ROOT, "%.1f MB", bytes / (1024.0 * 1024.0))
    }
}
