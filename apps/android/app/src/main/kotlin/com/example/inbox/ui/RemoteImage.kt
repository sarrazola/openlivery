package com.example.inbox.ui

import android.graphics.Bitmap
import androidx.compose.foundation.Image
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import com.example.inbox.media.AttachmentCache

/** An image fetched through the cache, with the session's credential when the server asks for one. */
@Composable
fun RemoteImage(url: String, token: String?, contentDescription: String?, modifier: Modifier = Modifier, contentScale: ContentScale = ContentScale.Crop, attempt: Int = 0, onState: ((Boolean?) -> Unit)? = null, placeholder: @Composable () -> Unit = {}) {
    var bitmap by remember(url) { mutableStateOf<Bitmap?>(null) }
    LaunchedEffect(url, attempt) {
        onState?.invoke(null)
        bitmap = runCatching { AttachmentCache.bitmap(url, token, force = attempt > 0) }.getOrNull()
        onState?.invoke(bitmap != null)
    }
    val current = bitmap
    if (current != null) Image(current.asImageBitmap(), contentDescription, modifier, contentScale = contentScale) else placeholder()
}
