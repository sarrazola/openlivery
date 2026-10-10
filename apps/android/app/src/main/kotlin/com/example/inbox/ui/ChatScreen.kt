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
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.automirrored.filled.Send
import androidx.compose.material.icons.filled.CloudOff
import androidx.compose.material.icons.filled.AutoAwesome
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Icon
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
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.inbox.AppModel
import com.example.inbox.api.ApiException
import com.example.inbox.api.Conversation
import com.example.inbox.api.ConversationDetail
import com.example.inbox.api.ConversationMode
import com.example.inbox.api.ConversationStatus
import com.example.inbox.api.Message
import com.example.inbox.api.PortalApi
import com.example.inbox.api.Session
import com.example.inbox.localization.ChatStrings
import com.example.inbox.localization.Strings
import com.example.inbox.rules.Conversations
import com.example.inbox.rules.InboxRules
import com.example.inbox.rules.When
import java.time.Instant
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

class ChatStore(conversation: Conversation) {
    var detail by mutableStateOf(ConversationDetail.opening(conversation))
    var loaded by mutableStateOf(false)
    var busy by mutableStateOf(false)
    var error by mutableStateOf<String?>(null)
    var hasNewMessages by mutableStateOf(false)
    var nearBottom = true
    var foreground = true
    var onExpired: (() -> Unit)? = null

    private var errorSource: String? = null
    private var loading = false
    private var mutating = false
    private var revision = 0
    private var lastMessageId: String? = null
    private var readSignature: String? = null

    private fun report(error: Exception, source: String = "action") {
        if (error is ApiException && error.isUnauthorized) onExpired?.invoke()
        errorSource = source
        this.error = (error as? ApiException)?.message ?: ChatStrings.current.updateFailed
    }

    private fun apply(next: ConversationDetail) {
        val nextId = next.messages.lastOrNull()?.id
        if (lastMessageId != null && nextId != lastMessageId && !nearBottom) hasNewMessages = true
        lastMessageId = nextId
        detail = next
    }

    suspend fun start(server: String, session: Session) {
        load(server, session)
        while (true) {
            delay(5_000)
            if (foreground) load(server, session)
        }
    }

    suspend fun load(server: String, session: Session, manual: Boolean = false) {
        if (loading || mutating || (!foreground && !manual)) return
        loading = true
        val generation = revision
        try {
            val next = PortalApi.conversation(server, session, detail.id)
            if (generation != revision) return
            apply(next)
            loaded = true
            if (manual || errorSource == "load") { error = null; errorSource = null }
            // Reading activity alone must not generate another write every poll.
            val signature = "${next.id}:${next.lastInboundAt ?: next.createdAt}"
            if (readSignature != signature) {
                PortalApi.markRead(server, session, next.id)
                readSignature = signature
            }
        } catch (error: CancellationException) {
            throw error
        } catch (error: Exception) {
            report(error, "load")
        } finally {
            loading = false
        }
    }

    suspend fun mutate(action: suspend () -> ConversationDetail): Boolean {
        if (mutating) return false
        mutating = true
        revision += 1
        busy = true
        error = null
        return try {
            apply(action())
            true
        } catch (error: CancellationException) {
            throw error
        } catch (error: Exception) {
            report(error)
            false
        } finally {
            mutating = false
            busy = false
        }
    }
}

/** The portal's case lifecycle and permissions, presented as a native thread. */
@Composable
fun ChatScreen(model: AppModel, conversation: Conversation, foreground: Boolean) {
    val c = ChatStrings.current
    val s = Strings.current
    val accent = LocalAccent.current
    val palette = accent.palette
    val session = model.session ?: return
    val server = model.server
    val scope = rememberCoroutineScope()
    val store = remember(conversation.id) { ChatStore(conversation) }
    var now by remember { mutableStateOf(Instant.now()) }
    var draft by remember(conversation.id) { mutableStateOf("") }
    var confirmResolve by remember { mutableStateOf(false) }
    val listState = rememberLazyListState()

    val detail = store.detail
    val who = Conversations.name(detail)
    val resolved = detail.status == ConversationStatus.RESOLVED
    val replyAllowed = store.loaded && InboxRules.canReply(detail, now)
    val windowClosed = InboxRules.isReplyWindowClosed(detail, now)
    val capabilities = InboxRules.capabilities(detail)

    BackHandler { model.back() }
    LaunchedEffect(conversation.id) { store.onExpired = { model.expireSession() }; store.start(server, session) }
    LaunchedEffect(foreground) { store.foreground = foreground; if (foreground) { now = Instant.now(); store.load(server, session) } }
    LaunchedEffect(Unit) { while (true) { delay(5_000); now = Instant.now() } }
    LaunchedEffect(detail.messages.lastOrNull()?.id, store.loaded) {
        if (store.loaded && detail.messages.isNotEmpty() && (store.nearBottom || listState.firstVisibleItemIndex == 0)) {
            listState.scrollToItem(detail.messages.size - 1)
        }
    }

    Column(Modifier.fillMaxSize().background(palette.canvas).statusBarsPadding().imePadding().navigationBarsPadding()) {
        // Header
        Row(Modifier.fillMaxWidth().background(palette.surface).padding(end = 12.dp), verticalAlignment = Alignment.CenterVertically) {
            Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = s.chat.back, tint = accent.color, modifier = Modifier.size(44.dp).clickable { model.back() }.padding(10.dp))
            Avatar(who, 40.dp, 14.dp, 18)
            Spacer(Modifier.width(10.dp))
            Column(Modifier.weight(1f).padding(vertical = 8.dp)) {
                Text(who, color = palette.ink, fontWeight = FontWeight.SemiBold, fontSize = 17.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
                Text(
                    listOfNotNull(Conversations.channelName(detail.channel), detail.assigneeName ?: if (detail.mode == ConversationMode.AI) s.inbox.aiHandling else null).joinToString(" · "),
                    color = palette.muted, fontSize = 12.sp, maxLines = 1, overflow = TextOverflow.Ellipsis,
                )
            }
            if (!resolved) {
                val label = if (detail.mode == ConversationMode.AI) s.chat.takeOver else s.chat.handBack
                Text(
                    label, color = accent.color, fontWeight = FontWeight.SemiBold, fontSize = 14.sp,
                    modifier = Modifier.clip(RoundedCornerShape(10.dp)).background(accent.tint()).clickable(enabled = store.loaded && !store.busy) {
                        scope.launch { store.mutate { PortalApi.setMode(server, session, detail.id, if (detail.mode == ConversationMode.AI) ConversationMode.HUMAN else ConversationMode.AI) } }
                    }.padding(horizontal = 12.dp, vertical = 8.dp),
                )
                Spacer(Modifier.width(8.dp))
                Text(
                    c.resolve, color = palette.muted, fontWeight = FontWeight.SemiBold, fontSize = 14.sp,
                    modifier = Modifier.clickable(enabled = store.loaded && !store.busy) { confirmResolve = true }.padding(6.dp),
                )
            }
        }
        Line()
        // Messages
        Box(Modifier.weight(1f).fillMaxWidth()) {
            if (!store.loaded) {
                if (store.error != null) Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) { Icon(Icons.Default.CloudOff, null, tint = palette.muted, modifier = Modifier.size(36.dp)) }
                else ChatSkeleton(s.inbox.loading)
            } else if (detail.messages.isEmpty()) {
                Centered(s.chat.empty)
            } else {
                LazyColumn(Modifier.fillMaxSize(), state = listState, contentPadding = androidx.compose.foundation.layout.PaddingValues(horizontal = 14.dp, vertical = 10.dp)) {
                    itemsIndexed(detail.messages, key = { _, m -> m.id }) { index, message ->
                        val previous = if (index > 0) detail.messages[index - 1] else null
                        if (previous == null || !When.sameDay(previous.createdAt, message.createdAt)) {
                            Box(Modifier.fillMaxWidth().padding(vertical = 14.dp), contentAlignment = Alignment.Center) {
                                Text(When.dayLabel(message.createdAt), color = palette.muted, fontSize = 12.sp, fontWeight = FontWeight.SemiBold,
                                    modifier = Modifier.clip(RoundedCornerShape(9.dp)).background(palette.surface).padding(horizontal = 12.dp, vertical = 5.dp))
                            }
                        }
                        MessageBubble(message, who, detail, server, session)
                        Spacer(Modifier.height(6.dp))
                    }
                }
            }
            if (store.hasNewMessages) {
                Box(Modifier.align(Alignment.BottomCenter).padding(bottom = 8.dp).clip(RoundedCornerShape(50)).background(palette.surface).clickable {
                    store.hasNewMessages = false; scope.launch { listState.animateScrollToItem(detail.messages.size - 1) }
                }.padding(horizontal = 14.dp, vertical = 10.dp)) { Text(c.newMessages, color = accent.color, fontWeight = FontWeight.SemiBold) }
            }
        }
        store.error?.let { error ->
            Row(Modifier.fillMaxWidth().background(palette.surface).padding(horizontal = 12.dp, vertical = 6.dp), verticalAlignment = Alignment.CenterVertically) {
                Text(error, color = palette.danger, fontSize = 13.sp, modifier = Modifier.weight(1f))
                Text(c.retry, color = accent.color, fontWeight = FontWeight.SemiBold, modifier = Modifier.clickable { scope.launch { store.load(server, session, manual = true) } }.padding(8.dp))
            }
        }
        // Footer
        Column(Modifier.fillMaxWidth().background(palette.surface)) {
            Line()
            when {
                resolved -> Text(c.resolvedHint, color = palette.muted, fontSize = 13.sp, modifier = Modifier.fillMaxWidth().padding(14.dp), textAlign = androidx.compose.ui.text.style.TextAlign.Center)
                detail.mode == ConversationMode.AI -> Row(Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 10.dp), verticalAlignment = Alignment.CenterVertically) {
                    Icon(Icons.Default.AutoAwesome, null, tint = palette.muted, modifier = Modifier.size(16.dp))
                    Spacer(Modifier.width(8.dp))
                    Text(s.inbox.aiHandling, color = palette.muted, fontSize = 14.sp, modifier = Modifier.weight(1f))
                    Text(
                        s.chat.takeOver, color = accent.onColor, fontWeight = FontWeight.SemiBold, fontSize = 14.sp,
                        modifier = Modifier.clip(RoundedCornerShape(10.dp)).background(accent.color).clickable(enabled = store.loaded && !store.busy) {
                            scope.launch { store.mutate { PortalApi.setMode(server, session, detail.id, ConversationMode.HUMAN) } }
                        }.padding(horizontal = 14.dp, vertical = 9.dp),
                    )
                }
                windowClosed -> Column(Modifier.padding(14.dp)) {
                    Text(c.windowClosed, color = palette.ink, fontWeight = FontWeight.SemiBold)
                    Text(c.windowHint, color = palette.muted, fontSize = 13.sp)
                }
                else -> ComposerView(
                    channel = detail.channel, capabilities = capabilities, textAllowed = replyAllowed, busy = store.busy,
                    draft = draft, onDraft = { draft = it }, onSavedReplies = null,
                    onSendText = { text ->
                        draft = ""
                        scope.launch { store.nearBottom = true; if (!store.mutate { PortalApi.reply(server, session, detail.id, text, null) }) draft = text }
                    },
                    onSendFile = { file, caption ->
                        draft = ""
                        scope.launch {
                            store.nearBottom = true
                            val sent = store.mutate { PortalApi.replyWithFile(server, session, detail.id, file, caption) }
                            if (sent) file.file.delete() else draft = caption
                        }
                    },
                )
            }
        }
    }

    if (confirmResolve) {
        AlertDialog(
            onDismissRequest = { confirmResolve = false },
            title = { Text(c.resolveTitle) }, text = { Text(c.resolveHint) },
            confirmButton = { TextButton({ confirmResolve = false; scope.launch { store.mutate { PortalApi.resolve(server, session, detail.id) } } }) { Text(c.resolveConfirm) } },
            dismissButton = { TextButton({ confirmResolve = false }) { Text(c.cancel) } },
        )
    }
}

@Composable
private fun MessageBubble(message: Message, who: String, detail: ConversationDetail, server: String, session: Session) {
    val accent = LocalAccent.current
    val palette = accent.palette
    val c = ChatStrings.current
    val s = Strings.current
    if (message.isActivity) {
        Box(Modifier.fillMaxWidth().padding(vertical = 6.dp, horizontal = 16.dp), contentAlignment = Alignment.Center) {
            Text("${c.activityLabel(message)} · ${When.time(message.createdAt)}", color = palette.muted, fontSize = 12.sp, textAlign = androidx.compose.ui.text.style.TextAlign.Center)
        }
        return
    }
    val outgoing = message.isOutgoing
    val ai = message.isAI
    val bubble = if (outgoing && !ai) accent.color else if (ai) accent.tint(if (accent.dark) 0.23f else 0.12f) else palette.bubbleIn
    val text = if (outgoing && !ai) accent.onColor else palette.ink
    val quoted = message.quotedMessageId?.let { id -> detail.messages.firstOrNull { it.id == id } }
    val delivery = InboxRules.delivery(message.deliveryStatus)
    val shape = RoundedCornerShape(topStart = 18.dp, topEnd = 18.dp, bottomStart = if (outgoing) 18.dp else 5.dp, bottomEnd = if (outgoing) 5.dp else 18.dp)
    Row(Modifier.fillMaxWidth().padding(vertical = 4.dp), horizontalArrangement = if (outgoing) Arrangement.End else Arrangement.Start) {
        Column(Modifier.widthIn(min = 94.dp, max = 320.dp).clip(shape).background(bubble).padding(start = 12.dp, end = 12.dp, top = 9.dp, bottom = 6.dp), verticalArrangement = Arrangement.spacedBy(5.dp)) {
            Text((message.senderName ?: if (outgoing) c.agent else who) + (if (ai) " · ${c.ai}" else ""), color = text.copy(alpha = 0.8f), fontSize = 11.sp, fontWeight = FontWeight.Bold)
            if (message.quotedMessageId != null) {
                Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(5.dp)).background(Color.Gray.copy(alpha = 0.12f)).padding(8.dp), verticalArrangement = Arrangement.spacedBy(3.dp)) {
                    Text(quoted?.senderName ?: if (quoted?.isOutgoing == true) c.agent else who, color = text, fontSize = 11.sp, fontWeight = FontWeight.Bold, maxLines = 1)
                    Text(quoted?.let { if (it.content.isEmpty()) (if (it.attachments.isEmpty()) c.unavailableQuote else s.attachment.generic) else it.content } ?: c.unavailableQuote, color = text, fontSize = 12.sp, maxLines = 3)
                }
            }
            message.attachments.forEach { attachment ->
                Box(Modifier.padding(vertical = 4.dp)) { AttachmentView(attachment, server, session, detail.id, outgoing && !ai) }
            }
            if (message.content.isNotEmpty()) Text(message.content, color = text, fontSize = 15.sp)
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End, verticalAlignment = Alignment.CenterVertically) {
                Text(When.time(message.createdAt), color = text.copy(alpha = 0.7f), fontSize = 10.sp)
                if (outgoing && (detail.channel == "whatsapp_cloud" || InboxRules.isSocialChannel(detail.channel)) && delivery != null) {
                    Spacer(Modifier.width(5.dp))
                    Icon(delivery.second, null, tint = text, modifier = Modifier.size(12.dp))
                    Spacer(Modifier.width(3.dp))
                    Text(c.delivery(delivery.first), color = text.copy(alpha = 0.8f), fontSize = 10.sp)
                }
            }
            message.deliveryError?.takeIf { it.isNotEmpty() }?.let { Text(it, color = text, fontSize = 11.sp) }
            val reactions = listOfNotNull(message.reaction, message.incomingReaction).filter { it.isNotEmpty() }
            if (reactions.isNotEmpty()) Row(horizontalArrangement = Arrangement.spacedBy(5.dp)) {
                reactions.forEach { Text(it, fontSize = 15.sp, modifier = Modifier.clip(RoundedCornerShape(50)).background(palette.surface).padding(horizontal = 7.dp, vertical = 2.dp)) }
            }
        }
    }
}
