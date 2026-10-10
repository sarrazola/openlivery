package com.example.inbox.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.systemBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.inbox.AppModel
import com.example.inbox.Brand
import com.example.inbox.api.Session
import com.example.inbox.localization.PrivacyStrings

/**
 * What the workspace does with a person's information, and their consent to it.
 *
 * Accepting is possible only once the whole disclosure has scrolled past, the
 * way a terms screen works, so nobody consents to a page they have not seen.
 */
@Composable
fun PrivacyScreen(model: AppModel, session: Session, server: String, accepted: Boolean) {
    val p = PrivacyStrings.current
    val accent = LocalAccent.current
    val palette = accent.palette
    val uriHandler = LocalUriHandler.current
    val scroll = rememberScrollState()
    val disclosure = session.privacy
    val unavailable = disclosure == null || disclosure.version.isEmpty()
    val serverHost = runCatching { java.net.URL(server).host }.getOrNull() ?: server
    var reachedEnd by remember { mutableStateOf(false) }
    var confirmWithdraw by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(scroll.value, scroll.maxValue) { if (scroll.value >= scroll.maxValue - 4) reachedEnd = true }

    Column(Modifier.fillMaxSize().background(palette.canvas).systemBarsPadding()) {
        Row(Modifier.fillMaxWidth().height(52.dp), verticalAlignment = Alignment.CenterVertically) {
            if (accepted) Text(p.back, color = accent.color, modifier = Modifier.clickable { model.leavePrivacy() }.padding(horizontal = 16.dp))
            Spacer(Modifier.weight(1f))
            Text(p.title, color = palette.ink, fontWeight = FontWeight.SemiBold, fontSize = 17.sp)
            Spacer(Modifier.weight(1f))
            if (accepted) Spacer(Modifier.width(60.dp))
        }
        Column(Modifier.weight(1f).verticalScroll(scroll).padding(20.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
            Text(if (accepted) p.reviewIntro else p.intro, color = palette.ink, fontSize = 22.sp, fontWeight = FontWeight.Bold)
            Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(palette.surface).padding(14.dp), verticalAlignment = Alignment.CenterVertically) {
                Avatar(session.branding.clientName, 44.dp, 14.dp, 18)
                Spacer(Modifier.width(12.dp))
                Column {
                    Text(p.account, color = palette.muted, fontSize = 12.sp)
                    Text(session.branding.clientName, color = palette.ink, fontWeight = FontWeight.SemiBold)
                    Text(serverHost, color = palette.muted, fontSize = 12.sp)
                }
            }
            Section(p.storedTitle, p.stored)
            Section(p.aiTitle, p.ai)
            Section(p.notificationsTitle, p.notifications)
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(p.destinationsTitle, color = palette.ink, fontWeight = FontWeight.Bold, fontSize = 15.sp)
                val destinations = disclosure?.destinations ?: emptyList()
                if (destinations.isNotEmpty()) {
                    destinations.forEach { destination ->
                        Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(palette.surface).padding(12.dp), verticalArrangement = Arrangement.spacedBy(3.dp)) {
                            Text(
                                when (destination.kind) { "ai" -> p.aiKind; "notification" -> p.notificationKind; else -> p.integrationKind }.uppercase(),
                                color = accent.color, fontSize = 11.sp, fontWeight = FontWeight.SemiBold,
                            )
                            Text(destination.name, color = palette.ink, fontWeight = FontWeight.SemiBold, fontSize = 15.sp)
                            if (destination.host.isNotEmpty()) Text(destination.host, color = palette.muted, fontSize = 12.sp)
                            if (destination.capabilities.isNotEmpty()) Text(destination.capabilities.joinToString(" · ") { p.capability(it) }, color = palette.muted, fontSize = 12.sp)
                        }
                    }
                } else if (disclosure != null) {
                    Text(p.noDestinations, color = palette.muted, fontSize = 13.sp)
                }
            }
            Row(horizontalArrangement = Arrangement.spacedBy(20.dp)) {
                Brand.privacyPolicyUrl?.let { url -> Text(p.policy, color = accent.color, fontWeight = FontWeight.SemiBold, fontSize = 13.sp, modifier = Modifier.clickable { uriHandler.openUri(url.toString()) }) }
                Brand.supportUrl?.let { url -> Text(p.support, color = accent.color, fontWeight = FontWeight.SemiBold, fontSize = 13.sp, modifier = Modifier.clickable { uriHandler.openUri(url.toString()) }) }
            }
            if (!accepted) Text(p.consent, color = palette.muted, fontSize = 13.sp)
            if (unavailable && !accepted) Text(p.unavailable, color = palette.danger, fontSize = 13.sp)
            error?.let { Text(it, color = palette.danger, fontSize = 13.sp) }
            Spacer(Modifier.height(4.dp))
        }
        Column(Modifier.fillMaxWidth().background(palette.surface).padding(horizontal = 20.dp, vertical = 12.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            if (!accepted) {
                PrimaryButton(p.accept, enabled = !unavailable && (reachedEnd || scroll.maxValue == 0)) {
                    try { model.acceptPrivacy() } catch (failure: Exception) { error = p.actionFailed }
                }
            }
            Box(Modifier.fillMaxWidth().height(44.dp).clickable { if (accepted) confirmWithdraw = true else model.withdrawPrivacy() }, contentAlignment = Alignment.Center) {
                Text(if (accepted) p.withdraw else p.decline, color = palette.danger, fontWeight = FontWeight.SemiBold, fontSize = 15.sp)
            }
        }
    }
    if (confirmWithdraw) {
        AlertDialog(
            onDismissRequest = { confirmWithdraw = false },
            title = { Text(p.withdrawTitle) }, text = { Text(p.withdrawBody) },
            confirmButton = { TextButton({ confirmWithdraw = false; model.withdrawPrivacy() }) { Text(p.withdraw, color = palette.danger) } },
            dismissButton = { TextButton({ confirmWithdraw = false }) { Text(p.cancel) } },
        )
    }
}

@Composable
private fun Section(title: String, body: String) {
    val palette = LocalAccent.current.palette
    Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(palette.surface).padding(14.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Text(title, color = palette.ink, fontWeight = FontWeight.Bold, fontSize = 15.sp)
        Text(body, color = palette.muted, fontSize = 14.sp, lineHeight = 20.sp)
    }
}
