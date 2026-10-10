package com.example.inbox.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.defaultMinSize
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.AccountCircle
import androidx.compose.material.icons.filled.AutoAwesome
import androidx.compose.material.icons.filled.Chat
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Language
import androidx.compose.material.icons.filled.Person
import androidx.compose.material.icons.filled.Phone
import androidx.compose.material.icons.filled.PhotoCamera
import androidx.compose.material.icons.filled.Science
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
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
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.inbox.AppModel
import com.example.inbox.api.ApiException
import com.example.inbox.api.Availability
import com.example.inbox.api.Conversation
import com.example.inbox.api.ConversationMode
import com.example.inbox.api.ConversationStatus
import com.example.inbox.api.InboxSummary
import com.example.inbox.api.PortalApi
import com.example.inbox.api.Session
import com.example.inbox.api.Team
import com.example.inbox.localization.Strings
import com.example.inbox.rules.Conversations
import com.example.inbox.rules.InboxRules
import com.example.inbox.rules.When
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

/** Loads, filters, pages and polls the list. */
class ConversationsStore {
    enum class Folder { ALL, UNREAD, MINE, AI }

    var items by mutableStateOf<List<Conversation>>(emptyList())
    var summary by mutableStateOf<InboxSummary?>(null)
    var teams by mutableStateOf<List<Team>>(emptyList())
    var status by mutableStateOf(ConversationStatus.OPEN)
    var folder by mutableStateOf(Folder.ALL)
    var team by mutableStateOf("")
    var channel by mutableStateOf("")
    var search by mutableStateOf("")
    var availability by mutableStateOf(Availability.AWAY)
    var availabilityBusy by mutableStateOf(false)
    var loaded by mutableStateOf(false)
    var loadingMore by mutableStateOf(false)
    var hasMore by mutableStateOf(false)
    var error by mutableStateOf<String?>(null)
    var onExpired: (() -> Unit)? = null

    private var nextOffset = 0
    private var requestId = 0
    private var fetching = false
    private var contextLoaded = false

    val query: String get() = search.trim()
    val filterActive: Boolean get() = team.isNotEmpty() || channel.isNotEmpty()
    /** Changing any of these restarts the list from the first page. */
    val filterKey: String get() = "${status.name}|$folder|$team|$channel|$query"

    fun clearFilters() { search = ""; folder = Folder.ALL; team = ""; channel = "" }

    private fun filters(limit: Int, offset: Int) = PortalApi.ConversationFilters(
        status = status, mode = if (folder == Folder.AI) ConversationMode.AI else null,
        assignee = if (folder == Folder.MINE) "me" else null, team = team.ifEmpty { null },
        unread = folder == Folder.UNREAD, channel = channel.ifEmpty { null }, search = query.ifEmpty { null }, limit = limit, offset = offset,
    )

    /** Runs for as long as the screen is on with this filter key. */
    suspend fun start(server: String, session: Session, scope: kotlinx.coroutines.CoroutineScope) {
        items = emptyList(); loaded = false; hasMore = false; error = null; nextOffset = 0; requestId += 1
        // Teams and availability are not needed to draw the list, so they load beside it.
        if (!contextLoaded) scope.launch { loadContext(server, session) }
        // Debounce typing: a search key change waits before hitting the server.
        if (query.isNotEmpty()) delay(300)
        load(server, session, reset = true)
        while (true) {
            delay(8_000)
            load(server, session)
        }
    }

    private suspend fun loadContext(server: String, session: Session) {
        try {
            teams = PortalApi.teams(server, session)
            PortalApi.members(server, session).firstOrNull { it.id == session.userId }?.let { availability = it.availability }
            contextLoaded = true
        } catch (error: ApiException) {
            if (error.isUnauthorized) onExpired?.invoke()
        } catch (error: Exception) {}
    }

    suspend fun load(server: String, session: Session, append: Boolean = false, reset: Boolean = false) {
        if (fetching && !reset) return
        requestId += 1
        val id = requestId
        fetching = true
        if (append) loadingMore = true
        try {
            val offset = if (append) nextOffset else 0
            val target = maxOf(PAGE, nextOffset)
            // Refresh every loaded row so changed assignments and resolved cases disappear.
            val limit = if (append) PAGE else minOf(target, 200)
            var rows = PortalApi.listConversations(server, session, filters(limit, offset))
            var exhausted = rows.size < limit
            if (!append && !exhausted && target > limit) {
                while (rows.size < target) {
                    val nextLimit = minOf(200, target - rows.size)
                    val next = PortalApi.listConversations(server, session, filters(nextLimit, rows.size))
                    rows = rows + next
                    exhausted = next.size < nextLimit
                    if (exhausted) break
                }
            }
            if (id != requestId) return
            nextOffset = offset + rows.size
            items = InboxRules.mergePages(if (append) items else emptyList(), rows)
            hasMore = !exhausted
            error = null
            runCatching { PortalApi.inboxSummary(server, session) }.getOrNull()?.let { if (id == requestId) summary = it }
        } catch (error: CancellationException) {
            throw error
        } catch (failure: ApiException) {
            if (id != requestId) return
            if (failure.isUnauthorized) onExpired?.invoke() else error = failure.message
        } catch (failure: Exception) {
            if (id != requestId) return
            error = Strings.current.list.loadFailed
        } finally {
            if (id == requestId) { fetching = false; loaded = true; loadingMore = false }
        }
    }

    suspend fun toggleAvailability(server: String, session: Session) {
        if (availabilityBusy) return
        availabilityBusy = true
        try {
            availability = PortalApi.setAvailability(server, session, if (availability == Availability.ONLINE) Availability.AWAY else Availability.ONLINE).availability
        } catch (failure: Exception) {
            error = failure.message
        } finally {
            availabilityBusy = false
        }
    }

    companion object { const val PAGE = 40 }
}

/** The inbox: open and resolved cases, folders, search, team and channel filters. */
@Composable
fun InboxScreen(model: AppModel, store: ConversationsStore, foreground: Boolean, onAccount: () -> Unit) {
    val s = Strings.current
    val accent = LocalAccent.current
    val palette = accent.palette
    val session = model.session ?: return
    val server = model.server
    val scope = rememberCoroutineScope()

    LaunchedEffect(store.filterKey, session.token) {
        store.onExpired = { model.expireSession() }
        store.start(server, session, scope)
    }
    LaunchedEffect(foreground) { if (foreground) store.load(server, session, reset = true) }
    LaunchedEffect(model.inboxPath.size) { if (model.inboxPath.isEmpty() && store.loaded) store.load(server, session, reset = true) }

    Column(Modifier.fillMaxSize().background(palette.surface).statusBarsPadding()) {
        // Header
        Row(Modifier.fillMaxWidth().padding(horizontal = 20.dp, vertical = 10.dp), verticalAlignment = Alignment.CenterVertically) {
            val logo = PortalApi.assetUrl(server, session.branding.clientLogoUrl ?: session.branding.agencyLogoUrl)
            if (logo != null) Box(Modifier.size(43.dp).clip(RoundedCornerShape(13.dp)), contentAlignment = Alignment.Center) {
                RemoteImage(logo, null, session.branding.clientName, Modifier.size(43.dp), androidx.compose.ui.layout.ContentScale.Fit) { Avatar(session.branding.clientName, 43.dp, 13.dp) }
            } else Avatar(session.branding.clientName, 43.dp, 13.dp)
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f)) {
                Text(session.branding.clientName, color = palette.muted, fontSize = 12.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
                Text(s.inbox.title, color = palette.ink, fontSize = 23.sp, fontWeight = FontWeight.Bold)
            }
            Icon(Icons.Default.AccountCircle, contentDescription = s.inbox.account, tint = accent.color, modifier = Modifier.size(32.dp).clickable(onClick = onAccount))
        }
        Line()
        // Controls
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            SearchField(store.search, s.inbox.search, { store.search = it })
            Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).background(palette.canvas).padding(3.dp)) {
                Segment("${s.inbox.open} ${store.summary?.open ?: ""}".trim(), store.status == ConversationStatus.OPEN, Modifier.weight(1f)) { store.status = ConversationStatus.OPEN; store.folder = ConversationsStore.Folder.ALL }
                Segment("${s.inbox.resolved} ${store.summary?.resolved ?: ""}".trim(), store.status == ConversationStatus.RESOLVED, Modifier.weight(1f)) { store.status = ConversationStatus.RESOLVED; store.folder = ConversationsStore.Folder.ALL }
            }
            if (store.status == ConversationStatus.OPEN) {
                val folders = if (session.userId == null) listOf(ConversationsStore.Folder.ALL, ConversationsStore.Folder.UNREAD, ConversationsStore.Folder.AI)
                else ConversationsStore.Folder.entries
                // Pills take the width their label needs and the row scrolls, so no language overflows.
                Row(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    folders.forEach { folder ->
                        val count = store.summary?.let { summary ->
                            when (folder) {
                                ConversationsStore.Folder.ALL -> summary.open; ConversationsStore.Folder.UNREAD -> summary.unread
                                ConversationsStore.Folder.MINE -> summary.mine; ConversationsStore.Folder.AI -> summary.ai
                            }
                        }?.takeIf { it > 0 }
                        val label = when (folder) {
                            ConversationsStore.Folder.ALL -> s.inbox.all; ConversationsStore.Folder.UNREAD -> s.inbox.unread
                            ConversationsStore.Folder.MINE -> s.inbox.mine; ConversationsStore.Folder.AI -> s.inbox.ai
                        }
                        Pill(label, count?.let { if (it > 99) "99+" else it.toString() }, store.folder == folder) { store.folder = folder }
                    }
                }
            }
        }
        store.error?.let { error ->
            Box(Modifier.padding(horizontal = 16.dp).padding(bottom = 8.dp)) {
                ErrorNotice(if (store.items.isEmpty()) error else s.inbox.connectionError, s.inbox.retry) { scope.launch { store.load(server, session, reset = true) } }
            }
        }
        if (!store.loaded && store.items.isEmpty()) {
            InboxSkeleton(s.inbox.loading)
        } else {
            val filtered = store.query.isNotEmpty() || store.filterActive || store.folder != ConversationsStore.Folder.ALL
            LazyColumn(Modifier.fillMaxSize()) {
                if (store.items.isEmpty()) {
                    item {
                        Column(Modifier.fillMaxWidth().padding(36.dp), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(8.dp)) {
                            Box(Modifier.size(70.dp).clip(RoundedCornerShape(25.dp)).background(accent.tint()), contentAlignment = Alignment.Center) {
                                Icon(if (store.status == ConversationStatus.RESOLVED) Icons.Default.CheckCircle else Icons.Default.Chat, null, tint = accent.color, modifier = Modifier.size(30.dp))
                            }
                            Text(if (filtered) s.inbox.noResults else s.list.emptyTitle, color = palette.ink, fontWeight = FontWeight.SemiBold, fontSize = 17.sp)
                            Text(if (filtered) s.inbox.noResultsBody else s.list.emptyBody, color = palette.muted, fontSize = 15.sp, textAlign = androidx.compose.ui.text.style.TextAlign.Center)
                            if (filtered) Text(s.inbox.clearFilters, color = accent.color, fontWeight = FontWeight.SemiBold, modifier = Modifier.clickable { store.clearFilters() }.padding(top = 8.dp))
                        }
                    }
                }
                items(store.items, key = { it.id }) { item ->
                    val unread = item.mode == ConversationMode.HUMAN && item.unreadCount > 0
                    Box(Modifier.fillMaxWidth().background(if (unread) accent.tint(0.035f) else palette.surface).clickable { model.openConversation(item) }) {
                        ConversationRow(item)
                    }
                    Box(Modifier.padding(start = 83.dp)) { Line() }
                    if (item.id == store.items.lastOrNull()?.id && store.hasMore) {
                        LaunchedEffect(item.id) { store.load(server, session, append = true) }
                    }
                }
                if (store.hasMore) {
                    item {
                        Box(Modifier.fillMaxWidth().height(56.dp).clickable { scope.launch { store.load(server, session, append = true) } }, contentAlignment = Alignment.Center) {
                            if (store.loadingMore) CircularProgressIndicator(color = accent.color, strokeWidth = 2.dp, modifier = Modifier.size(20.dp))
                            else Text(s.inbox.loadMore, color = accent.color)
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun Segment(label: String, selected: Boolean, modifier: Modifier, onClick: () -> Unit) {
    val palette = LocalAccent.current.palette
    Box(
        modifier.height(32.dp).clip(RoundedCornerShape(8.dp)).background(if (selected) palette.surface else androidx.compose.ui.graphics.Color.Transparent).clickable(onClick = onClick),
        contentAlignment = Alignment.Center,
    ) { Text(label, color = palette.ink, fontSize = 14.sp, fontWeight = if (selected) FontWeight.SemiBold else FontWeight.Normal) }
}

fun channelIcon(channel: String): ImageVector = when {
    InboxRules.isWhatsApp(channel) -> Icons.Default.Phone
    channel == "instagram" -> Icons.Default.PhotoCamera
    channel == "messenger" -> Icons.Default.Chat
    channel == "playground" -> Icons.Default.Science
    else -> Icons.Default.Language
}

/** One conversation in the list. */
@Composable
fun ConversationRow(item: Conversation) {
    val s = Strings.current
    val accent = LocalAccent.current
    val palette = accent.palette
    val name = Conversations.name(item)
    val unread = item.mode == ConversationMode.HUMAN && item.unreadCount > 0
    val owner = if (item.mode == ConversationMode.AI) s.inbox.aiHandling else item.assigneeName ?: s.inbox.legacyHuman
    Row(Modifier.fillMaxWidth().padding(horizontal = 20.dp, vertical = 14.dp), verticalAlignment = Alignment.Top) {
        Box {
            Avatar(name)
            Box(
                Modifier.align(Alignment.BottomEnd).padding(end = 0.dp).size(20.dp).clip(CircleShape).background(palette.surface),
                contentAlignment = Alignment.Center,
            ) {
                Icon(channelIcon(item.channel), null, tint = if (item.channel.startsWith("whatsapp")) Theme.whatsappGreen else palette.muted, modifier = Modifier.size(12.dp))
            }
        }
        Spacer(Modifier.width(13.dp))
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(name, color = palette.ink, fontWeight = if (unread) FontWeight.ExtraBold else FontWeight.SemiBold, fontSize = 17.sp, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f, fill = false))
                Spacer(Modifier.width(8.dp))
                Text(When.rowLabel(InboxRules.timestamp(item)), color = if (unread) accent.color else palette.muted, fontSize = 11.sp)
            }
            Row(verticalAlignment = Alignment.Top) {
                Text(item.preview.ifEmpty { s.list.noMessages }, color = if (unread) palette.ink else palette.muted, fontSize = 15.sp, maxLines = 2, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f))
                if (unread) {
                    Spacer(Modifier.width(8.dp))
                    Box(Modifier.defaultMinSize(20.dp, 20.dp).clip(RoundedCornerShape(50)).background(accent.color).padding(horizontal = 6.dp), contentAlignment = Alignment.Center) {
                        Text(if (item.unreadCount > 99) "99+" else item.unreadCount.toString(), color = androidx.compose.ui.graphics.Color.White, fontSize = 10.sp, fontWeight = FontWeight.Bold)
                    }
                }
            }
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp), modifier = Modifier.padding(top = 3.dp)) {
                Icon(
                    when { item.status == ConversationStatus.RESOLVED -> Icons.Default.CheckCircle; item.mode == ConversationMode.AI -> Icons.Default.AutoAwesome; else -> Icons.Default.Person },
                    null, tint = palette.muted, modifier = Modifier.size(12.dp),
                )
                Text((if (item.status == ConversationStatus.RESOLVED) s.inbox.resolved else owner) + (item.teamName?.let { " · $it" } ?: ""), color = palette.muted, fontSize = 11.sp, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f))
                Text(Conversations.channelLabel(item.channel), color = palette.muted, fontSize = 10.sp)
            }
        }
    }
}
