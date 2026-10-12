package com.example.inbox.ui

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.Logout
import androidx.compose.material.icons.filled.Bolt
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.Description
import androidx.compose.material.icons.filled.Groups
import androidx.compose.material.icons.filled.Label
import androidx.compose.material.icons.filled.OpenInNew
import androidx.compose.material.icons.filled.VerifiedUser
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
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
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.inbox.AppModel
import com.example.inbox.Brand
import com.example.inbox.api.ApiException
import com.example.inbox.api.Availability
import com.example.inbox.api.CannedReply
import com.example.inbox.api.CannedReplyCreate
import com.example.inbox.api.CannedReplyUpdate
import com.example.inbox.api.ContactTag
import com.example.inbox.api.ContactTagCreate
import com.example.inbox.api.ContactTagUpdate
import com.example.inbox.api.PortalApi
import com.example.inbox.api.Team
import com.example.inbox.api.Template
import com.example.inbox.localization.PrivacyStrings
import com.example.inbox.localization.SettingsStrings
import com.example.inbox.localization.Strings
import com.example.inbox.localization.WorkspaceStrings
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.launch

/** The portal's settings: the workspace catalogues (teams, tags, saved replies, templates) and the person's own account. */
@Composable
fun SettingsHost(model: AppModel, onSignOut: () -> Unit) {
    var page by remember { mutableStateOf("") }
    var editingTeam by remember { mutableStateOf<Team?>(null) }
    var teamEditor by remember { mutableStateOf(false) }
    val s = SettingsStrings.current
    BackHandler(enabled = page.isNotEmpty()) { if (teamEditor) teamEditor = false else page = "" }
    Column(Modifier.fillMaxSize().statusBarsPadding()) {
        when {
            page.isEmpty() -> SettingsMenu(model, onSignOut) { page = it }
            page == "teams" && teamEditor -> TeamEditor(model, editingTeam) { teamEditor = false }
            page == "teams" -> Column {
                TopBar(s.teams, s.cancel, onBack = { page = "" }); Line()
                TeamsPanel(model) { team -> editingTeam = team; teamEditor = true }
            }
            page == "tags" -> TagsScreen(model) { page = "" }
            page == "canned" -> CannedRepliesScreen(model) { page = "" }
            page == "templates" -> TemplatesScreen(model) { page = "" }
        }
    }
}

@Composable
private fun SettingsMenu(model: AppModel, onSignOut: () -> Unit, open: (String) -> Unit) {
    val s = SettingsStrings.current
    val p = PrivacyStrings.current
    val w = WorkspaceStrings.current
    val accent = LocalAccent.current
    val palette = accent.palette
    val uriHandler = LocalUriHandler.current
    val session = model.session ?: return
    val server = model.server
    var availability by remember { mutableStateOf(Availability.AWAY) }
    var busy by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    LaunchedEffect(Unit) { runCatching { PortalApi.members(server, session) }.getOrNull()?.firstOrNull { it.id == session.userId }?.let { availability = it.availability } }

    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(18.dp)) {
        Text(s.title, color = palette.ink, fontSize = 28.sp, fontWeight = FontWeight.Bold)
        Text(s.subtitle, color = palette.muted, fontSize = 13.sp, modifier = Modifier.padding(bottom = 16.dp))
        Text(s.workspace.uppercase(), color = palette.muted, fontSize = 12.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(bottom = 4.dp))
        Column(Modifier.clip(RoundedCornerShape(14.dp)).background(palette.canvas).padding(horizontal = 14.dp)) {
            SheetRow(Icons.Default.Groups, s.teams) { open("teams") }; Line()
            SheetRow(Icons.Default.Label, s.tags) { open("tags") }; Line()
            SheetRow(Icons.Default.Bolt, s.canned) { open("canned") }; Line()
            SheetRow(Icons.Default.Description, s.templates) { open("templates") }
        }
        Text(s.account.uppercase(), color = palette.muted, fontSize = 12.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(top = 22.dp, bottom = 4.dp))
        Column(Modifier.clip(RoundedCornerShape(14.dp)).background(palette.canvas).padding(horizontal = 14.dp)) {
            Row(Modifier.fillMaxWidth().padding(vertical = 12.dp), verticalAlignment = Alignment.CenterVertically) {
                Avatar(session.branding.clientName, 40.dp, 13.dp, 16)
                Spacer(Modifier.width(12.dp))
                Column { Text(session.userName.ifEmpty { session.branding.agencyName }, color = palette.ink, fontWeight = FontWeight.SemiBold); Text(session.branding.clientName, color = palette.muted, fontSize = 12.sp) }
            }
            if (session.userId != null) {
                Line()
                Row(Modifier.fillMaxWidth().height(56.dp).clickable(enabled = !busy) {
                    scope.launch { busy = true; runCatching { PortalApi.setAvailability(server, session, if (availability == Availability.ONLINE) Availability.AWAY else Availability.ONLINE) }.getOrNull()?.let { availability = it.availability }; busy = false }
                }, verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    CircleDot(if (availability == Availability.ONLINE) Theme.onlineGreen else palette.subtle)
                    Text(if (availability == Availability.ONLINE) Strings.current.inbox.online else Strings.current.inbox.away, color = palette.ink, modifier = Modifier.weight(1f))
                    Text(if (availability == Availability.ONLINE) w.goAway else w.goOnline, color = accent.color, fontSize = 13.sp)
                }
            }
            Line()
            SheetRow(Icons.Default.VerifiedUser, p.title) { model.showPrivacy() }
            Brand.privacyPolicyUrl?.let { url -> Line(); SheetRow(Icons.Default.OpenInNew, p.policy) { uriHandler.openUri(url.toString()) } }
            Brand.supportUrl?.let { url -> Line(); SheetRow(Icons.Default.OpenInNew, p.support) { uriHandler.openUri(url.toString()) } }
            Line()
            SheetRow(Icons.AutoMirrored.Filled.Logout, s.signOut, danger = true, onClick = onSignOut)
        }
        Text(
            "${com.example.inbox.Brand.name} ${com.example.inbox.BuildConfig.VERSION_NAME} (${com.example.inbox.BuildConfig.VERSION_CODE}) · ${com.example.inbox.BuildConfig.BUILD_STAMP}",
            color = palette.subtle, fontSize = 11.sp, modifier = Modifier.padding(top = 18.dp),
        )
        Spacer(Modifier.height(30.dp))
    }
}

// MARK: Tags

val tagColors = listOf("#6b7280", "#ef4444", "#f97316", "#eab308", "#22c55e", "#14b8a6", "#3b82f6", "#8b5cf6", "#ec4899")

@Composable
private fun TagsScreen(model: AppModel, onBack: () -> Unit) {
    val s = SettingsStrings.current
    val accent = LocalAccent.current
    val palette = accent.palette
    val session = model.session ?: return
    val server = model.server
    val canManage = session.has("tags.manage")
    var tags by remember { mutableStateOf<List<ContactTag>>(emptyList()) }
    var loading by remember { mutableStateOf(true) }
    var error by remember { mutableStateOf<String?>(null) }
    var editing by remember { mutableStateOf<ContactTag?>(null) }
    var creating by remember { mutableStateOf(false) }
    var deleting by remember { mutableStateOf<ContactTag?>(null) }
    var reload by remember { mutableIntStateOf(0) }
    val scope = rememberCoroutineScope()

    LaunchedEffect(reload) {
        try { tags = PortalApi.tags(server, session); error = null } catch (f: CancellationException) { throw f }
        catch (f: ApiException) { if (f.isUnauthorized) model.expireSession(); error = f.message } catch (f: Exception) { error = s.loadFailed }
        loading = false
    }

    if (creating || editing != null) {
        TagEditor(model, editing, onDone = { creating = false; editing = null; reload += 1 })
        return
    }
    Column(Modifier.fillMaxSize()) {
        TopBar(s.tags, s.cancel, onBack) { if (canManage) Text("+", color = accent.color, fontSize = 24.sp, modifier = Modifier.clickable { creating = true }.padding(8.dp)) }
        Line()
        Column(Modifier.verticalScroll(rememberScrollState()).padding(20.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text(if (canManage) s.tagsHint else s.readOnly, color = palette.muted, fontSize = 13.sp)
            error?.let { ErrorNotice(it, s.retry) { reload += 1 } }
            if (loading) ContactsSkeleton(Strings.current.inbox.loading, 4) else if (tags.isEmpty()) Text(s.noTags, color = palette.muted)
            tags.forEach { tag ->
                Row(Modifier.fillMaxWidth().clickable(enabled = canManage) { editing = tag }.padding(vertical = 10.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    CircleDot(Theme.hex(tag.color), 12.dp)
                    Column(Modifier.weight(1f)) {
                        Text(tag.name, color = palette.ink, fontWeight = FontWeight.SemiBold)
                        val route = tag.routeTeamName ?: tag.routeAssigneeName
                        Text("${tag.contactCount} ${s.contacts}" + (route?.let { " · ${s.routesTo} $it" } ?: ""), color = palette.muted, fontSize = 12.sp)
                    }
                    if (canManage) Icon(Icons.Default.Delete, contentDescription = s.delete, tint = palette.subtle, modifier = Modifier.size(20.dp).clickable { deleting = tag })
                }
                Line()
            }
        }
    }
    deleting?.let { tag ->
        AlertDialog(onDismissRequest = { deleting = null }, title = { Text(s.deleteTag) }, text = { Text(s.deleteTagBody) },
            confirmButton = { TextButton({ scope.launch { runCatching { PortalApi.deleteTag(server, session, tag.id); tags = tags.filter { it.id != tag.id } }.onFailure { error = (it as? ApiException)?.message ?: s.saveFailed }; deleting = null } }) { Text(s.delete, color = palette.danger) } },
            dismissButton = { TextButton({ deleting = null }) { Text(s.cancel) } })
    }
}

@Composable
private fun TagEditor(model: AppModel, tag: ContactTag?, onDone: () -> Unit) {
    val s = SettingsStrings.current
    val accent = LocalAccent.current
    val palette = accent.palette
    val session = model.session ?: return
    val server = model.server
    var name by remember { mutableStateOf(tag?.name ?: "") }
    var color by remember { mutableStateOf(tag?.color ?: tagColors[0]) }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    val scope = rememberCoroutineScope()
    BackHandler { if (!busy) onDone() }
    Column(Modifier.fillMaxSize().imePadding()) {
        TopBar(if (tag == null) s.newTag else s.editTag, s.cancel, onBack = { if (!busy) onDone() })
        Line()
        Column(Modifier.padding(22.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            FieldLabel(s.tagName)
            FormTextField(name, { name = it }, enabled = !busy)
            FieldLabel(s.tagColor)
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                tagColors.forEach { value ->
                    Box(Modifier.size(30.dp).clip(CircleShape).background(Theme.hex(value)).clickable { color = value }
                        .then(if (color == value) Modifier.border(2.dp, palette.ink, CircleShape) else Modifier))
                }
            }
            error?.let { Text(it, color = palette.danger) }
            Spacer(Modifier.height(12.dp))
            PrimaryButton(s.save, enabled = name.isNotBlank(), busy = busy) {
                scope.launch {
                    busy = true; error = null
                    try {
                        if (tag != null) PortalApi.updateTag(server, session, tag.id, ContactTagUpdate(name.trim(), color)) else PortalApi.createTag(server, session, ContactTagCreate(name.trim(), color))
                        onDone()
                    } catch (f: ApiException) { error = if (f.status == 409) s.duplicate else f.message } catch (f: Exception) { error = s.saveFailed }
                    busy = false
                }
            }
        }
    }
}

// MARK: Saved replies

@Composable
private fun CannedRepliesScreen(model: AppModel, onBack: () -> Unit) {
    val s = SettingsStrings.current
    val accent = LocalAccent.current
    val palette = accent.palette
    val session = model.session ?: return
    val server = model.server
    val canManage = session.has("canned.manage")
    var items by remember { mutableStateOf<List<CannedReply>>(emptyList()) }
    var loading by remember { mutableStateOf(true) }
    var error by remember { mutableStateOf<String?>(null) }
    var editing by remember { mutableStateOf<CannedReply?>(null) }
    var creating by remember { mutableStateOf(false) }
    var deleting by remember { mutableStateOf<CannedReply?>(null) }
    var reload by remember { mutableIntStateOf(0) }
    val scope = rememberCoroutineScope()

    LaunchedEffect(reload) {
        try { items = PortalApi.cannedReplies(server, session); error = null } catch (f: CancellationException) { throw f }
        catch (f: ApiException) { if (f.isUnauthorized) model.expireSession(); error = f.message } catch (f: Exception) { error = s.loadFailed }
        loading = false
    }

    if (creating || editing != null) {
        CannedReplyEditor(model, editing, onDone = { creating = false; editing = null; reload += 1 })
        return
    }
    Column(Modifier.fillMaxSize()) {
        TopBar(s.canned, s.cancel, onBack) { if (canManage) Text("+", color = accent.color, fontSize = 24.sp, modifier = Modifier.clickable { creating = true }.padding(8.dp)) }
        Line()
        Column(Modifier.verticalScroll(rememberScrollState()).padding(20.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text(if (canManage) s.cannedHint else s.readOnly, color = palette.muted, fontSize = 13.sp)
            error?.let { ErrorNotice(it, s.retry) { reload += 1 } }
            if (loading) ContactsSkeleton(Strings.current.inbox.loading, 4) else if (items.isEmpty()) Text(s.noCanned, color = palette.muted)
            items.forEach { item ->
                Row(Modifier.fillMaxWidth().clickable(enabled = canManage) { editing = item }.padding(vertical = 10.dp), verticalAlignment = Alignment.Top, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        Text("/${item.shortcut}", color = accent.color, fontWeight = FontWeight.SemiBold)
                        Text(item.content, color = palette.ink, fontSize = 14.sp, maxLines = 3)
                    }
                    if (canManage) Icon(Icons.Default.Delete, contentDescription = s.delete, tint = palette.subtle, modifier = Modifier.size(20.dp).clickable { deleting = item })
                }
                Line()
            }
        }
    }
    deleting?.let { item ->
        AlertDialog(onDismissRequest = { deleting = null }, title = { Text(s.deleteReply) }, text = { Text(s.deleteReplyBody) },
            confirmButton = { TextButton({ scope.launch { runCatching { PortalApi.deleteCannedReply(server, session, item.id); items = items.filter { it.id != item.id } }.onFailure { error = (it as? ApiException)?.message ?: s.saveFailed }; deleting = null } }) { Text(s.delete, color = palette.danger) } },
            dismissButton = { TextButton({ deleting = null }) { Text(s.cancel) } })
    }
}

@Composable
private fun CannedReplyEditor(model: AppModel, reply: CannedReply?, onDone: () -> Unit) {
    val s = SettingsStrings.current
    val palette = LocalAccent.current.palette
    val session = model.session ?: return
    val server = model.server
    var shortcut by remember { mutableStateOf(reply?.shortcut ?: "") }
    var content by remember { mutableStateOf(reply?.content ?: "") }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    val scope = rememberCoroutineScope()
    val valid = Regex("^[a-z0-9_-]{1,60}$").matches(shortcut) && content.isNotBlank()
    BackHandler { if (!busy) onDone() }
    Column(Modifier.fillMaxSize().imePadding()) {
        TopBar(if (reply == null) s.newReply else s.editReply, s.cancel, onBack = { if (!busy) onDone() })
        Line()
        Column(Modifier.verticalScroll(rememberScrollState()).padding(22.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            FieldLabel(s.shortcut)
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                Text("/", color = palette.muted, fontSize = 20.sp)
                FormTextField(shortcut, { shortcut = it.lowercase() }, placeholder = "saludo", enabled = !busy)
            }
            Text(s.shortcutHint, color = palette.muted, fontSize = 12.sp)
            FieldLabel(s.content)
            FormTextField(content, { content = it }, multiline = true, enabled = !busy)
            Text(s.variablesHint, color = palette.muted, fontSize = 12.sp)
            error?.let { Text(it, color = palette.danger) }
            Spacer(Modifier.height(12.dp))
            PrimaryButton(s.save, enabled = valid, busy = busy) {
                scope.launch {
                    busy = true; error = null
                    try {
                        if (reply != null) PortalApi.updateCannedReply(server, session, reply.id, CannedReplyUpdate(shortcut, content.trim())) else PortalApi.createCannedReply(server, session, CannedReplyCreate(shortcut, content.trim()))
                        onDone()
                    } catch (f: ApiException) { error = if (f.status == 409) s.duplicate else f.message } catch (f: Exception) { error = s.saveFailed }
                    busy = false
                }
            }
        }
    }
}

// MARK: WhatsApp templates

@Composable
private fun TemplatesScreen(model: AppModel, onBack: () -> Unit) {
    val s = SettingsStrings.current
    val accent = LocalAccent.current
    val palette = accent.palette
    val session = model.session ?: return
    val server = model.server
    val canManage = session.has("templates.manage")
    var items by remember { mutableStateOf<List<Template>>(emptyList()) }
    var loading by remember { mutableStateOf(true) }
    var error by remember { mutableStateOf<String?>(null) }
    var deleting by remember { mutableStateOf<Template?>(null) }
    var reload by remember { mutableIntStateOf(0) }
    val scope = rememberCoroutineScope()

    LaunchedEffect(reload) {
        try { items = PortalApi.templates(server, session); error = null } catch (f: CancellationException) { throw f }
        catch (f: ApiException) { if (f.isUnauthorized) model.expireSession(); error = if (f.status == 404 || f.status == 400) s.noLine else f.message } catch (f: Exception) { error = s.loadFailed }
        loading = false
    }
    Column(Modifier.fillMaxSize()) {
        TopBar(s.templates, s.cancel, onBack)
        Line()
        Column(Modifier.verticalScroll(rememberScrollState()).padding(20.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text(if (canManage) s.templatesHint else s.readOnly, color = palette.muted, fontSize = 13.sp)
            if (canManage) Text(s.templatesWebOnly, color = palette.muted, fontSize = 13.sp)
            error?.let { ErrorNotice(it, s.retry) { reload += 1 } }
            if (loading) ContactsSkeleton(Strings.current.inbox.loading, 4) else if (items.isEmpty() && error == null) Text(s.noTemplates, color = palette.muted)
            items.forEach { item ->
                Column(Modifier.fillMaxWidth().padding(vertical = 8.dp), verticalArrangement = Arrangement.spacedBy(5.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text(item.name, color = palette.ink, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f))
                        val tone = when (item.status) { "APPROVED" -> Theme.resolvedGreen; "REJECTED" -> palette.danger; else -> palette.muted }
                        Text(s.status(item.status), color = tone, fontSize = 11.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.clip(RoundedCornerShape(50)).background(tone.copy(alpha = 0.12f)).padding(horizontal = 7.dp, vertical = 3.dp))
                        if (canManage) { Spacer(Modifier.width(10.dp)); Icon(Icons.Default.Delete, contentDescription = s.delete, tint = palette.subtle, modifier = Modifier.size(20.dp).clickable { deleting = item }) }
                    }
                    Text("${item.language} · ${item.category.lowercase().replaceFirstChar { it.uppercase() }}", color = palette.muted, fontSize = 12.sp)
                    Text(item.body, color = palette.ink, fontSize = 14.sp, maxLines = 4)
                    item.rejectedReason?.takeIf { it.isNotEmpty() }?.let { Text(it, color = palette.danger, fontSize = 12.sp) }
                }
                Line()
            }
        }
    }
    deleting?.let { item ->
        AlertDialog(onDismissRequest = { deleting = null }, title = { Text(s.deleteTemplate) }, text = { Text(s.deleteTemplateBody) },
            confirmButton = { TextButton({ scope.launch { runCatching { PortalApi.deleteTemplate(server, session, item.name); items = items.filter { it.name != item.name } }.onFailure { error = (it as? ApiException)?.message ?: s.saveFailed }; deleting = null } }) { Text(s.delete, color = palette.danger) } },
            dismissButton = { TextButton({ deleting = null }) { Text(s.cancel) } })
    }
}
