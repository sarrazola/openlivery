package com.example.inbox.ui

import androidx.activity.compose.BackHandler
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
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.Logout
import androidx.compose.material.icons.filled.BarChart
import androidx.compose.material.icons.filled.Chat
import androidx.compose.material.icons.filled.OpenInNew
import androidx.compose.material.icons.filled.People
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.filled.SwapHoriz
import androidx.compose.material.icons.filled.VerifiedUser
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Icon
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.inbox.AppModel
import com.example.inbox.Brand
import com.example.inbox.api.ApiException
import com.example.inbox.api.Availability
import com.example.inbox.api.Contact
import com.example.inbox.api.PortalApi
import com.example.inbox.localization.ContactsStrings
import com.example.inbox.localization.PrivacyStrings
import com.example.inbox.localization.Strings
import com.example.inbox.localization.WorkspaceStrings
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

/** The signed-in app: four tabs, each keeping its own stack. */
@OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class)
@Composable
fun MainTabs(model: AppModel, foreground: Boolean) {
    val s = Strings.current
    val accent = LocalAccent.current
    val palette = accent.palette
    val inboxStore = remember { ConversationsStore() }
    var accountSheet by remember { mutableStateOf(false) }
    var confirmSignOut by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    val uriHandler = LocalUriHandler.current
    val session = model.session ?: return
    val server = model.server

    val openChat = when (model.tab) { AppModel.Tab.CONTACTS -> model.contactsPath.lastOrNull(); else -> model.inboxPath.lastOrNull() }
    if (openChat != null) {
        ChatScreen(model, openChat, foreground)
        return
    }
    BackHandler(enabled = model.tab != AppModel.Tab.INBOX) { model.tab = AppModel.Tab.INBOX }

    Column(Modifier.fillMaxSize().background(palette.surface)) {
        Box(Modifier.weight(1f)) {
            when (model.tab) {
                AppModel.Tab.INBOX -> InboxScreen(model, inboxStore, foreground) { accountSheet = true }
                AppModel.Tab.CONTACTS -> ContactsScreen(model)
                AppModel.Tab.REPORTS -> ReportsScreen(model)
                AppModel.Tab.SETTINGS -> SettingsHost(model) { confirmSignOut = true }
            }
        }
        Line()
        Row(Modifier.fillMaxWidth().background(palette.surface).navigationBarsPadding().height(58.dp)) {
            TabItem(Icons.Default.Chat, s.inbox.tabTitle, model.tab == AppModel.Tab.INBOX, Modifier.weight(1f)) { model.tab = AppModel.Tab.INBOX }
            TabItem(Icons.Default.People, s.inbox.contacts, model.tab == AppModel.Tab.CONTACTS, Modifier.weight(1f)) { model.tab = AppModel.Tab.CONTACTS }
            TabItem(Icons.Default.BarChart, WorkspaceStrings.current.reports, model.tab == AppModel.Tab.REPORTS, Modifier.weight(1f)) { model.tab = AppModel.Tab.REPORTS }
            TabItem(Icons.Default.Settings, WorkspaceStrings.current.settings, model.tab == AppModel.Tab.SETTINGS, Modifier.weight(1f)) { model.tab = AppModel.Tab.SETTINGS }
        }
    }

    if (accountSheet) {
        val p = PrivacyStrings.current
        ModalBottomSheet(onDismissRequest = { accountSheet = false }, containerColor = palette.surface) {
            Column(Modifier.padding(horizontal = 20.dp).padding(bottom = 30.dp)) {
                Text(session.userName.ifEmpty { session.branding.agencyName }, color = palette.ink, fontSize = 20.sp, fontWeight = FontWeight.SemiBold)
                Text(session.branding.clientName, color = palette.muted, modifier = Modifier.padding(bottom = 8.dp))
                if (session.userId != null) {
                    SheetRow(null, if (inboxStore.availability == Availability.ONLINE) s.inbox.online else s.inbox.away, leading = {
                        CircleDot(if (inboxStore.availability == Availability.ONLINE) Theme.whatsappGreen else palette.subtle)
                    }, trailing = Icons.Default.SwapHoriz) { scope.launch { inboxStore.toggleAvailability(server, session) } }
                    Text(s.inbox.availabilityHint, color = palette.muted, fontSize = 13.sp)
                }
                Spacer(Modifier.height(12.dp))
                SheetRow(Icons.Default.VerifiedUser, p.title) { accountSheet = false; model.showPrivacy() }
                Brand.privacyPolicyUrl?.let { url -> SheetRow(Icons.Default.OpenInNew, p.policy) { uriHandler.openUri(url.toString()) } }
                Brand.supportUrl?.let { url -> SheetRow(Icons.Default.OpenInNew, p.support) { uriHandler.openUri(url.toString()) } }
                Spacer(Modifier.height(12.dp))
                SheetRow(Icons.AutoMirrored.Filled.Logout, s.inbox.signOut, danger = true) { accountSheet = false; confirmSignOut = true }
            }
        }
    }
    if (confirmSignOut) {
        AlertDialog(
            onDismissRequest = { confirmSignOut = false },
            title = { Text(s.inbox.signOutTitle) },
            confirmButton = { TextButton({ confirmSignOut = false; model.signOut() }) { Text(s.inbox.signOut, color = palette.danger) } },
            dismissButton = { TextButton({ confirmSignOut = false }) { Text(s.inbox.cancel) } },
        )
    }
}

@Composable
fun SheetRow(icon: ImageVector?, label: String, danger: Boolean = false, leading: (@Composable () -> Unit)? = null, trailing: ImageVector? = null, onClick: () -> Unit) {
    val accent = LocalAccent.current
    val palette = accent.palette
    Row(Modifier.fillMaxWidth().height(56.dp).clickable(onClick = onClick), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        if (leading != null) leading() else if (icon != null) Icon(icon, null, tint = if (danger) palette.danger else accent.color, modifier = Modifier.size(22.dp))
        Text(label, color = if (danger) palette.danger else palette.ink, fontSize = 16.sp, modifier = Modifier.weight(1f))
        if (trailing != null) Icon(trailing, null, tint = accent.color, modifier = Modifier.size(20.dp))
    }
}

@Composable
private fun TabItem(icon: ImageVector, label: String, selected: Boolean, modifier: Modifier, onClick: () -> Unit) {
    val accent = LocalAccent.current
    val palette = accent.palette
    Column(modifier.fillMaxSize().clickable(onClick = onClick), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Center) {
        Icon(icon, null, tint = if (selected) accent.color else palette.muted, modifier = Modifier.size(24.dp))
        Text(label, color = if (selected) accent.color else palette.muted, fontSize = 11.sp, fontWeight = if (selected) FontWeight.SemiBold else FontWeight.Normal)
    }
}

@Composable
fun PlaceholderScreen(title: String, body: String) {
    val palette = LocalAccent.current.palette
    Column(Modifier.fillMaxSize().statusBarsPadding().padding(18.dp)) {
        Text(title, color = palette.ink, fontSize = 28.sp, fontWeight = FontWeight.Bold)
        Centered(body)
    }
}
