package com.example.inbox.ui

import android.Manifest
import android.content.pm.PackageManager
import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.Send
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Bolt
import androidx.compose.material.icons.filled.Cancel
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Description
import androidx.compose.material.icons.filled.Mic
import androidx.compose.material.icons.filled.Pause
import androidx.compose.material.icons.filled.PhotoCamera
import androidx.compose.material.icons.filled.PhotoLibrary
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.ContextCompat
import androidx.core.content.FileProvider
import com.example.inbox.api.ChannelCapabilities
import com.example.inbox.api.OutgoingFile
import com.example.inbox.localization.ChatStrings
import com.example.inbox.localization.Strings
import com.example.inbox.media.AttachmentCache
import com.example.inbox.media.MimeTypes
import com.example.inbox.media.Recorder
import com.example.inbox.rules.InboxRules
import java.io.File
import kotlinx.coroutines.delay

/**
 * Text, a staged photo, video, file or voice note, and the controls that stage
 * them. The channel's capabilities decide what is offered; the server decides
 * what goes through.
 */
@OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class)
@Composable
fun ComposerView(
    channel: String, capabilities: ChannelCapabilities, textAllowed: Boolean, busy: Boolean,
    draft: String, onDraft: (String) -> Unit,
    onSavedReplies: (() -> Unit)?,
    onSendText: (String) -> Unit, onSendFile: (OutgoingFile, String) -> Unit,
) {
    val s = Strings.current.composer
    val c = ChatStrings.current
    val accent = LocalAccent.current
    val palette = accent.palette
    val context = LocalContext.current
    val recorder = remember { Recorder(context) }
    var pending by remember { mutableStateOf<OutgoingFile?>(null) }
    var attachMenu by remember { mutableStateOf(false) }
    var notice by remember { mutableStateOf<String?>(null) }
    var cameraTarget by remember { mutableStateOf<File?>(null) }

    val mediaAllowed = capabilities.image == true || capabilities.video == true
    val canAttach = mediaAllowed || capabilities.file == true
    val fileAllowed = pending?.let { InboxRules.acceptsAttachment(channel, capabilities, it.mime) } ?: true
    val canSend = !busy && fileAllowed && (pending != null || draft.isNotBlank()) && (pending != null || textAllowed)

    fun stage(uri: Uri, fallbackName: String) {
        val resolver = context.contentResolver
        val mime = resolver.getType(uri) ?: "application/octet-stream"
        var name = fallbackName
        resolver.query(uri, arrayOf(android.provider.OpenableColumns.DISPLAY_NAME), null, null, null)?.use { cursor ->
            if (cursor.moveToFirst()) cursor.getString(0)?.let { name = it }
        }
        val target = AttachmentCache.stagingFile(name.replace("/", "_"))
        try {
            resolver.openInputStream(uri)?.use { input -> target.outputStream().use { input.copyTo(it) } } ?: throw IllegalStateException()
            pending = OutgoingFile(target, name, mime)
        } catch (error: Exception) {
            target.delete(); notice = c.pickFailed
        }
    }

    val pickMedia = rememberLauncherForActivityResult(ActivityResultContracts.PickVisualMedia()) { uri -> uri?.let { stage(it, "photo.jpg") } }
    val pickFile = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri -> uri?.let { stage(it, "file") } }
    val takePicture = rememberLauncherForActivityResult(ActivityResultContracts.TakePicture()) { ok ->
        val target = cameraTarget
        if (ok && target != null && target.length() > 0) pending = OutgoingFile(target, "photo.jpg", "image/jpeg") else target?.delete()
        cameraTarget = null
    }
    val cameraPermission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        if (granted) {
            val target = AttachmentCache.stagingFile("photo.jpg")
            cameraTarget = target
            takePicture.launch(FileProvider.getUriForFile(context, context.packageName + ".files", target))
        }
    }
    val micPermission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        if (granted) { if (!recorder.start()) notice = c.micUnavailable } else notice = c.micUnavailable
    }

    LaunchedEffect(recorder.state) { while (recorder.state == Recorder.State.RECORDING) { recorder.tick(); delay(150) } }

    Column(Modifier.fillMaxWidth().background(palette.surface)) {
        pending?.let { file ->
            Row(Modifier.fillMaxWidth().padding(12.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Icon(if (file.isAudio) Icons.Default.Mic else if (file.mime.startsWith("image/")) Icons.Default.PhotoLibrary else Icons.Default.Description, null, tint = accent.color, modifier = Modifier.size(24.dp))
                Column(Modifier.weight(1f)) {
                    Text(if (file.isAudio) c.audioReady else file.name, color = palette.ink, fontSize = 15.sp, fontWeight = FontWeight.SemiBold, maxLines = 1)
                    Text(if (fileAllowed) c.attached else c.unsupportedAttachment, color = if (fileAllowed) palette.muted else palette.danger, fontSize = 12.sp)
                }
                Icon(Icons.Default.Cancel, contentDescription = c.removeFile, tint = palette.muted, modifier = Modifier.size(24.dp).clickable(enabled = !busy) { file.file.delete(); pending = null })
            }
            Line()
        }
        notice?.let { Text(it, color = palette.danger, fontSize = 12.sp, modifier = Modifier.padding(horizontal = 14.dp, vertical = 4.dp).clickable { notice = null }) }
        if (recorder.state != Recorder.State.IDLE) {
            val paused = recorder.state == Recorder.State.PAUSED
            Row(Modifier.fillMaxWidth().padding(horizontal = 10.dp, vertical = 8.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                Icon(Icons.Default.Close, contentDescription = s.discardLabel, tint = palette.muted, modifier = Modifier.size(40.dp).clickable { recorder.stop(keep = false) }.padding(8.dp))
                CircleDot(if (paused) palette.subtle else palette.danger, 10.dp)
                Text(Recorder.clock(recorder.elapsedMs), color = palette.ink, fontSize = 16.sp, fontWeight = FontWeight.SemiBold)
                Box(Modifier.weight(1f).height(18.dp), contentAlignment = Alignment.CenterStart) {
                    Box(Modifier.fillMaxWidth(if (paused) 0f else recorder.level.coerceIn(0.05f, 1f)).height(4.dp).clip(RoundedCornerShape(2.dp)).background(accent.color))
                }
                Icon(if (paused) Icons.Default.PlayArrow else Icons.Default.Pause, contentDescription = if (paused) s.resume else s.pause, tint = accent.color, modifier = Modifier.size(40.dp).clickable { if (paused) recorder.resume() else recorder.pause() }.padding(8.dp))
                SendButton(busy = false, enabled = true, label = s.sendVoice) {
                    val file = recorder.stop(keep = true)
                    if (file == null) notice = c.recordingTooShort else pending = file
                }
            }
        } else {
            Row(Modifier.fillMaxWidth().padding(horizontal = 8.dp, vertical = 8.dp), verticalAlignment = Alignment.Bottom, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                val attachEnabled = !busy && (canAttach || (onSavedReplies != null && textAllowed))
                Icon(Icons.Default.Add, contentDescription = s.attach, tint = if (attachEnabled) palette.muted else palette.line, modifier = Modifier.size(40.dp).clickable(enabled = attachEnabled) { attachMenu = true }.padding(8.dp))
                val micEnabled = !busy && capabilities.audio == true && pending == null
                Icon(Icons.Default.Mic, contentDescription = c.recordAudio, tint = if (micEnabled) palette.muted else palette.line, modifier = Modifier.size(40.dp).clickable(enabled = micEnabled) {
                    if (ContextCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) { if (!recorder.start()) notice = c.micUnavailable }
                    else micPermission.launch(Manifest.permission.RECORD_AUDIO)
                }.padding(8.dp))
                Box(Modifier.weight(1f).clip(RoundedCornerShape(19.dp)).background(palette.canvas).padding(horizontal = 15.dp, vertical = 11.dp), contentAlignment = Alignment.CenterStart) {
                    if (draft.isEmpty()) Text(if (pending != null) c.caption else s.placeholder, color = palette.subtle, fontSize = 16.sp)
                    BasicTextField(
                        value = draft, onValueChange = onDraft, enabled = !busy && (textAllowed || pending != null), maxLines = 5,
                        textStyle = TextStyle(color = palette.ink, fontSize = 16.sp), cursorBrush = SolidColor(accent.color), modifier = Modifier.fillMaxWidth(),
                    )
                }
                SendButton(busy = busy, enabled = canSend, label = if (pending?.isAudio == true) s.sendVoice else s.send) {
                    val file = pending
                    val text = draft.trim()
                    if (file != null) { pending = null; onSendFile(file, text) } else if (text.isNotEmpty()) onSendText(text)
                }
            }
        }
    }

    if (attachMenu) {
        ModalBottomSheet(onDismissRequest = { attachMenu = false }, containerColor = palette.surface) {
            Column(Modifier.padding(horizontal = 20.dp).padding(bottom = 30.dp)) {
                Text(s.sheetTitle, color = palette.ink, fontWeight = FontWeight.SemiBold, fontSize = 17.sp, modifier = Modifier.padding(bottom = 8.dp))
                if (onSavedReplies != null && textAllowed) SheetRow(Icons.Default.Bolt, c.canned) { attachMenu = false; onSavedReplies() }
                if (mediaAllowed) {
                    SheetRow(Icons.Default.PhotoLibrary, s.fromLibrary) {
                        attachMenu = false
                        val type = when { capabilities.image == true && capabilities.video == true -> ActivityResultContracts.PickVisualMedia.ImageAndVideo; capabilities.video == true -> ActivityResultContracts.PickVisualMedia.VideoOnly; else -> ActivityResultContracts.PickVisualMedia.ImageOnly }
                        pickMedia.launch(PickVisualMediaRequest(type))
                    }
                    if (capabilities.image == true) SheetRow(Icons.Default.PhotoCamera, s.fromCamera) { attachMenu = false; cameraPermission.launch(Manifest.permission.CAMERA) }
                }
                if (canAttach) SheetRow(Icons.Default.Description, c.file) { attachMenu = false; pickFile.launch(arrayOf("*/*")) }
            }
        }
    }
}

@Composable
private fun SendButton(busy: Boolean, enabled: Boolean, label: String, onClick: () -> Unit) {
    val accent = LocalAccent.current
    Box(Modifier.size(40.dp).clip(CircleShape).background(if (enabled) accent.color else accent.color.copy(alpha = 0.35f)).clickable(enabled = enabled && !busy, onClick = onClick), contentAlignment = Alignment.Center) {
        if (busy) CircularProgressIndicator(color = accent.onColor, strokeWidth = 2.dp, modifier = Modifier.size(18.dp))
        else Icon(Icons.AutoMirrored.Filled.Send, contentDescription = label, tint = accent.onColor, modifier = Modifier.size(18.dp))
    }
}
