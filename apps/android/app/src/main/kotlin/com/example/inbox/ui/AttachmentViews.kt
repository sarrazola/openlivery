package com.example.inbox.ui

import android.content.Intent
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Description
import androidx.compose.material.icons.filled.Pause
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.Videocam
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import androidx.core.content.FileProvider
import com.example.inbox.api.Attachment
import com.example.inbox.api.PortalApi
import com.example.inbox.api.Session
import com.example.inbox.localization.ChatStrings
import com.example.inbox.localization.Strings
import com.example.inbox.media.AttachmentCache
import com.example.inbox.media.AudioPlayer
import com.example.inbox.media.MimeTypes
import com.example.inbox.media.Recorder
import java.io.File
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

/** One attachment inside a bubble: a picture, a voice note or a file to open. */
@Composable
fun AttachmentView(attachment: Attachment, server: String, session: Session, conversationId: String, outgoing: Boolean) {
    val url = PortalApi.attachmentUrl(server, session, conversationId, attachment.id)
    when {
        attachment.mime.startsWith("image/") -> ImageAttachment(url, session.token)
        attachment.mime.startsWith("audio/") || attachment.kind == "audio" -> AudioAttachment(url, session.token, attachment, outgoing)
        else -> FileAttachment(url, session.token, attachment, outgoing)
    }
}

@Composable
private fun ImageAttachment(url: String, token: String) {
    val c = ChatStrings.current
    val palette = LocalAccent.current.palette
    var expanded by remember { mutableStateOf(false) }
    var attempt by remember { mutableIntStateOf(0) }
    var failed by remember { mutableStateOf(false) }
    Box(Modifier.size(230.dp).clip(RoundedCornerShape(12.dp)).background(palette.bubbleIn).clickable { if (failed) attempt += 1 else expanded = true }, contentAlignment = Alignment.Center) {
        RemoteImage(url, token, c.viewImage, Modifier.fillMaxSize(), ContentScale.Crop, attempt, onState = { failed = it == false }) {
            if (failed) Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(Strings.current.attachment.imageUnavailable, color = palette.muted, fontSize = 13.sp)
                Text(c.retry, color = palette.ink, fontWeight = FontWeight.SemiBold)
            } else CircularProgressIndicator(color = palette.muted, strokeWidth = 2.dp, modifier = Modifier.size(24.dp))
        }
    }
    if (expanded) {
        Dialog(onDismissRequest = { expanded = false }, properties = DialogProperties(usePlatformDefaultWidth = false)) {
            Box(Modifier.fillMaxSize().background(Color.Black)) {
                RemoteImage(url, token, c.viewImage, Modifier.fillMaxSize(), ContentScale.Fit)
                Icon(Icons.Default.Close, contentDescription = c.close, tint = Color.White, modifier = Modifier.align(Alignment.TopEnd).padding(18.dp).size(32.dp).clickable { expanded = false })
            }
        }
    }
}

/** The voice-note layout, shared by the loading and playable states. */
@Composable
fun VoiceNoteRow(control: Color, onControl: Color, busy: Boolean, playing: Boolean, progress: Float, label: String, onClick: (() -> Unit)?) {
    Row(Modifier.widthIn(min = 200.dp).padding(vertical = 2.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        Box(Modifier.size(36.dp).clip(CircleShape).background(control).clickable(enabled = onClick != null) { onClick?.invoke() }, contentAlignment = Alignment.Center) {
            if (busy) CircularProgressIndicator(color = onControl, strokeWidth = 2.dp, modifier = Modifier.size(18.dp))
            else Icon(if (playing) Icons.Default.Pause else Icons.Default.PlayArrow, null, tint = onControl, modifier = Modifier.size(20.dp))
        }
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(7.dp)) {
            Box(Modifier.fillMaxWidth().height(3.dp).clip(RoundedCornerShape(2.dp)).background(control.copy(alpha = 0.3f))) {
                Box(Modifier.fillMaxWidth(progress.coerceIn(0f, 1f)).height(3.dp).background(control))
            }
            Text(label, color = control.copy(alpha = 0.85f), fontSize = 12.sp)
        }
    }
}

/** Downloads a voice note once, then plays it from disk. */
@Composable
private fun AudioAttachment(url: String, token: String, attachment: Attachment, outgoing: Boolean) {
    val c = ChatStrings.current
    val accent = LocalAccent.current
    val palette = accent.palette
    val control = if (outgoing) accent.onColor else accent.color
    val onControl = if (outgoing) accent.color else accent.onColor
    var file by remember(url) { mutableStateOf<File?>(null) }
    var failed by remember(url) { mutableStateOf(false) }
    var attempt by remember { mutableIntStateOf(0) }
    val scope = rememberCoroutineScope()
    val playing = file != null && AudioPlayer.playingPath == file!!.path
    LaunchedEffect(url, attempt) {
        failed = false
        file = runCatching { AttachmentCache.download(url, token, MimeTypes.audioExtension(attachment.mime)) }.getOrNull()
        if (file == null) failed = true
    }
    LaunchedEffect(playing) { while (playing) { AudioPlayer.tick(); delay(200) } }
    val label = when {
        failed -> c.audioFailed
        file == null -> Strings.current.inbox.loading
        playing -> Recorder.clock((AudioPlayer.progress * AudioPlayer.durationMs).toLong()) + " / " + Recorder.clock(AudioPlayer.durationMs.toLong())
        else -> Recorder.clock(remember(file) { AudioPlayer.duration(file!!).toLong() })
    }
    VoiceNoteRow(control, onControl, busy = file == null && !failed, playing = playing && AudioPlayer.isPlaying, progress = if (playing) AudioPlayer.progress else 0f, label = label) {
        if (failed) attempt += 1 else file?.let { scope.launch { AudioPlayer.toggle(it) } }
    }
}

/** A document or video: downloaded on tap and handed to the app that opens it. */
@Composable
private fun FileAttachment(url: String, token: String, attachment: Attachment, outgoing: Boolean) {
    val c = ChatStrings.current
    val accent = LocalAccent.current
    val palette = accent.palette
    val context = LocalContext.current
    val text = if (outgoing) accent.onColor else palette.ink
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    val scope = rememberCoroutineScope()
    val video = attachment.kind == "video" || attachment.mime.startsWith("video/")
    Row(
        Modifier.widthIn(min = 200.dp).clip(RoundedCornerShape(10.dp)).background(text.copy(alpha = 0.08f)).clickable(enabled = !busy) {
            scope.launch {
                busy = true; error = null
                try {
                    val ext = MimeTypes.extensionFor(attachment.filename, if (video) "mp4" else "bin")
                    val file = AttachmentCache.download(url, token, ext)
                    val uri = FileProvider.getUriForFile(context, context.packageName + ".files", file)
                    val intent = Intent(Intent.ACTION_VIEW).setDataAndType(uri, attachment.mime.ifEmpty { "*/*" }).addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                    context.startActivity(Intent.createChooser(intent, c.openFile))
                } catch (failure: Exception) { error = c.attachmentFailed }
                busy = false
            }
        }.padding(10.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        if (busy) CircularProgressIndicator(color = text, strokeWidth = 2.dp, modifier = Modifier.size(20.dp))
        else Icon(if (video) Icons.Default.Videocam else Icons.Default.Description, null, tint = text, modifier = Modifier.size(22.dp))
        Column(Modifier.weight(1f)) {
            Text(attachment.filename ?: Strings.current.attachment.generic, color = text, fontSize = 14.sp, fontWeight = FontWeight.SemiBold, maxLines = 1, overflow = TextOverflow.Ellipsis)
            Text(error ?: MimeTypes.humanSize(attachment.sizeBytes), color = text.copy(alpha = 0.75f), fontSize = 12.sp)
        }
    }
}
