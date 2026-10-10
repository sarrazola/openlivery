package com.example.inbox.ui

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
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
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Chat
import androidx.compose.material.icons.filled.Edit
import androidx.compose.material.icons.filled.PersonAdd
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
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.inbox.AppModel
import com.example.inbox.api.ApiException
import com.example.inbox.api.Contact
import com.example.inbox.api.ContactCreate
import com.example.inbox.api.ContactTag
import com.example.inbox.api.ContactUpdate
import com.example.inbox.api.Conversation
import com.example.inbox.api.ConversationMode
import com.example.inbox.api.ConversationStatus
import com.example.inbox.api.PortalApi
import com.example.inbox.api.PortalChannel
import com.example.inbox.api.Session
import com.example.inbox.localization.ContactsStrings
import com.example.inbox.localization.Strings
import com.example.inbox.rules.Conversations
import com.example.inbox.rules.DialCodes
import com.example.inbox.rules.InboxRules
import com.example.inbox.rules.When
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

class ContactsStore {
    var items by mutableStateOf<List<Contact>>(emptyList())
    var search by mutableStateOf("")
    var loading by mutableStateOf(true)
    var loadingMore by mutableStateOf(false)
    var hasMore by mutableStateOf(false)
    var error by mutableStateOf<String?>(null)
    var selected by mutableStateOf<Contact?>(null)
    var history by mutableStateOf<List<Conversation>>(emptyList())
    var channels by mutableStateOf<List<PortalChannel>>(emptyList())
    var detailLoading by mutableStateOf(false)
    var detailError by mutableStateOf<String?>(null)
    var busy by mutableStateOf(false)
    var onExpired: (() -> Unit)? = null

    private var generation = 0
    private var detailGeneration = 0
    private var offset = 0

    val query: String get() = search.trim()

    fun name(contact: Contact): String = contact.name.trim().ifEmpty { contact.phone ?: contact.email ?: ContactsStrings.current.unnamed }

    private fun message(error: Exception, fallback: String): String {
        if (error is ApiException) { if (error.isUnauthorized) onExpired?.invoke(); return error.message ?: fallback }
        return fallback
    }

    suspend fun load(server: String, session: Session) {
        generation += 1
        val current = generation
        loadingMore = false
        try {
            val rows = PortalApi.contacts(server, session, query.ifEmpty { null }, PAGE, 0)
            if (current != generation) return
            items = rows; offset = rows.size; hasMore = rows.size == PAGE; error = null
        } catch (e: CancellationException) { throw e }
        catch (e: Exception) { if (current == generation) error = message(e, ContactsStrings.current.loadFailed) }
        if (current == generation) loading = false
    }

    suspend fun loadMore(server: String, session: Session) {
        if (!hasMore || loadingMore || loading) return
        loadingMore = true
        val current = generation
        try {
            val rows = PortalApi.contacts(server, session, query.ifEmpty { null }, PAGE, offset)
            if (current != generation) return
            val seen = items.map { it.id }.toMutableSet()
            items = items + rows.filter { seen.add(it.id) }
            offset += rows.size; hasMore = rows.size == PAGE; error = null
        } catch (e: CancellationException) { throw e }
        catch (e: Exception) { if (current == generation) error = message(e, ContactsStrings.current.loadFailed) }
        if (current == generation) loadingMore = false
    }

    suspend fun open(contact: Contact, server: String, session: Session) {
        selected = contact; history = emptyList(); channels = emptyList(); detailLoading = true; detailError = null
        detailGeneration += 1
        val current = detailGeneration
        try {
            val fresh = PortalApi.contact(server, session, contact.id)
            val rows = PortalApi.contactConversations(server, session, contact.id)
            val lines = runCatching { PortalApi.channels(server, session) }.getOrDefault(emptyList())
            if (current != detailGeneration) return
            selected = fresh; history = rows; channels = lines.filter { InboxRules.isWhatsApp(it.channel) }
        } catch (e: CancellationException) { throw e }
        catch (e: Exception) { if (current == detailGeneration) detailError = message(e, ContactsStrings.current.loadFailed) }
        if (current == detailGeneration) detailLoading = false
    }

    suspend fun save(patch: ContactUpdate, creating: Boolean, server: String, session: Session): Boolean {
        if (busy) return false
        busy = true; detailError = null
        return try {
            val saved = if (creating) PortalApi.createContact(server, session, ContactCreate(patch.name, patch.phone ?: "", patch.email, patch.notes))
            else PortalApi.updateContact(server, session, selected?.id ?: return false, patch)
            selected = saved
            load(server, session)
            open(saved, server, session)
            true
        } catch (e: ApiException) {
            detailError = if (e.status == 409) ContactsStrings.current.duplicatePhone else message(e, ContactsStrings.current.saveFailed); false
        } catch (e: Exception) { detailError = ContactsStrings.current.saveFailed; false }
        finally { busy = false }
    }

    companion object { const val PAGE = 40 }
}

/** A native contact directory sharing the portal's contact and case records. */
@Composable
fun ContactsScreen(model: AppModel) {
    val cs = ContactsStrings.current
    val s = Strings.current
    val accent = LocalAccent.current
    val palette = accent.palette
    val session = model.session ?: return
    val server = model.server
    val store = remember { ContactsStore() }
    var panel by remember { mutableStateOf("") }   // "", contact, new, edit, start, tags
    val scope = rememberCoroutineScope()

    LaunchedEffect(store.query) {
        store.onExpired = { model.expireSession() }
        if (store.query.isNotEmpty()) delay(300)
        store.load(server, session)
    }

    if (panel.isNotEmpty()) {
        ContactPanel(model, store, panel, onPanel = { panel = it }, onClose = { panel = "" }) { conversation -> panel = ""; model.openConversation(conversation) }
        return
    }

    Column(Modifier.fillMaxSize().statusBarsPadding()) {
        Row(Modifier.padding(18.dp), verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text(cs.title, color = palette.ink, fontSize = 28.sp, fontWeight = FontWeight.Bold)
                Text(cs.subtitle, color = palette.muted, fontSize = 13.sp)
            }
            Box(Modifier.size(44.dp).clip(RoundedCornerShape(14.dp)).background(accent.tint()).clickable { store.detailError = null; panel = "new" }, contentAlignment = Alignment.Center) {
                Icon(Icons.Default.PersonAdd, contentDescription = cs.newContact, tint = accent.color)
            }
        }
        Box(Modifier.padding(horizontal = 20.dp).padding(bottom = 12.dp)) { SearchField(store.search, cs.search, { store.search = it }) }
        store.error?.let { Box(Modifier.padding(horizontal = 16.dp).padding(bottom = 8.dp)) { ErrorNotice(it, cs.retry) { scope.launch { store.load(server, session) } } } }
        if (store.loading && store.items.isEmpty()) {
            ContactsSkeleton(s.inbox.loading)
        } else {
            LazyColumn(Modifier.fillMaxSize()) {
                if (store.items.isEmpty()) item {
                    Column(Modifier.fillMaxWidth().padding(30.dp), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text(if (store.query.isEmpty()) cs.empty else cs.noMatches, color = palette.ink, fontWeight = FontWeight.SemiBold, fontSize = 18.sp)
                        if (store.query.isEmpty()) Text(cs.emptyHint, color = palette.muted, textAlign = TextAlign.Center)
                    }
                }
                items(store.items, key = { it.id }) { contact ->
                    Row(Modifier.fillMaxWidth().clickable { panel = "contact"; scope.launch { store.open(contact, server, session) } }.padding(horizontal = 20.dp, vertical = 12.dp), verticalAlignment = Alignment.CenterVertically) {
                        Avatar(store.name(contact), fontSize = 20)
                        Spacer(Modifier.width(12.dp))
                        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                            Text(store.name(contact), color = palette.ink, fontWeight = FontWeight.SemiBold)
                            val line = listOfNotNull(contact.phone?.let { DialCodes.format(it) }, contact.email).filter { it.isNotEmpty() }.joinToString(" · ")
                            if (line.isNotEmpty()) Text(line, color = palette.muted, fontSize = 12.sp, maxLines = 1)
                            Text("${contact.conversationCount} ${if (contact.conversationCount == 1) cs.conversation else cs.conversations}" + (if (contact.openCount > 0) " · ${contact.openCount} ${if (contact.openCount == 1) cs.openCase else cs.openCases}" else ""), color = palette.muted, fontSize = 12.sp)
                        }
                    }
                    Box(Modifier.padding(start = 20.dp)) { Line() }
                    if (contact.id == store.items.lastOrNull()?.id && store.hasMore) LaunchedEffect(contact.id) { store.loadMore(server, session) }
                }
            }
        }
    }
}

/** The full-screen panel that shows, creates, edits a contact, picks its tags or starts a conversation. */
@OptIn(androidx.compose.foundation.layout.ExperimentalLayoutApi::class)
@Composable
private fun ContactPanel(model: AppModel, store: ContactsStore, panel: String, onPanel: (String) -> Unit, onClose: () -> Unit, onOpen: (Conversation) -> Unit) {
    val cs = ContactsStrings.current
    val accent = LocalAccent.current
    val palette = accent.palette
    val session = model.session ?: return
    val server = model.server
    val scope = rememberCoroutineScope()
    val selected = store.selected
    val nested = panel == "edit" || panel == "start" || panel == "tags"
    val title = when (panel) { "new" -> cs.newContact; "edit" -> cs.edit; "start" -> cs.start; "tags" -> cs.editTags; else -> selected?.let { store.name(it) } ?: "" }
    BackHandler { if (!store.busy) { if (nested) { store.detailError = null; onPanel("contact") } else onClose() } }

    Column(Modifier.fillMaxSize().statusBarsPadding().imePadding()) {
        TopBar(title, if (nested) cs.back else cs.close, onBack = { if (!store.busy) { if (nested) { store.detailError = null; onPanel("contact") } else onClose() } })
        Line()
        when (panel) {
            "new", "edit" -> ContactEditor(if (panel == "edit") selected else null, store.busy, store.detailError) { patch ->
                scope.launch { if (store.save(patch, panel == "new", server, session)) onPanel("contact") }
            }
            "tags" -> selected?.let { contact -> ContactTagsPicker(model, contact) { updated -> store.selected = updated; onPanel("contact") } }
            "start" -> selected?.let { contact -> StartConversation(model, contact, store.channels, store.history, onOpen) }
            else -> selected?.let { contact ->
                Column(Modifier.verticalScroll(rememberScrollState()).padding(22.dp)) {
                    store.detailError?.let { Box(Modifier.padding(bottom = 12.dp)) { ErrorNotice(it, cs.retry) { scope.launch { store.open(contact, server, session) } } } }
                    Column(Modifier.fillMaxWidth().padding(vertical = 16.dp), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        Avatar(store.name(contact), 80.dp, 28.dp, 34)
                        Text(store.name(contact), color = palette.ink, fontSize = 28.sp, fontWeight = FontWeight.Bold, textAlign = TextAlign.Center)
                        contact.phone?.takeIf { it.isNotEmpty() }?.let { Text(DialCodes.format(it), color = palette.muted) }
                        contact.email?.takeIf { it.isNotEmpty() }?.let { Text(it, color = palette.muted) }
                    }
                    Row(Modifier.fillMaxWidth().padding(vertical = 18.dp), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        ActionTile(cs.edit, Icons.Default.Edit, enabled = !store.detailLoading && !store.busy, Modifier.weight(1f)) { store.detailError = null; onPanel("edit") }
                        ActionTile(cs.start, Icons.Default.Chat, enabled = !store.detailLoading && !contact.phone.isNullOrEmpty() && store.channels.isNotEmpty(), Modifier.weight(1f)) { store.detailError = null; onPanel("start") }
                    }
                    if (contact.phone.isNullOrEmpty()) Text(cs.noPhone, color = palette.muted, fontSize = 13.sp)
                    if (!store.detailLoading && !contact.phone.isNullOrEmpty() && store.channels.isEmpty()) Text(cs.noLine, color = palette.muted, fontSize = 13.sp)
                    Row(Modifier.fillMaxWidth().padding(top = 24.dp, bottom = 12.dp), verticalAlignment = Alignment.CenterVertically) {
                        SectionTitle(cs.tags, Modifier.weight(1f))
                        Text(cs.editTags, color = accent.color, fontWeight = FontWeight.SemiBold, fontSize = 14.sp, modifier = Modifier.clickable(enabled = !store.detailLoading && !store.busy) { store.detailError = null; onPanel("tags") })
                    }
                    val tags = contact.tags ?: emptyList()
                    if (tags.isEmpty()) Text(cs.noTags, color = palette.muted)
                    else FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) { tags.forEach { Chip(it.name, Theme.hex(it.color)) } }
                    SectionTitle(cs.notes, Modifier.padding(top = 24.dp, bottom = 12.dp))
                    Text(contact.notes.ifEmpty { cs.noNotes }, color = if (contact.notes.isEmpty()) palette.muted else palette.ink)
                    SectionTitle(cs.history, Modifier.padding(top = 24.dp, bottom = 12.dp))
                    if (store.detailLoading) ContactsSkeleton(Strings.current.inbox.loading, 2)
                    else if (store.history.isEmpty()) Text(cs.noHistory, color = palette.muted)
                    store.history.forEach { conversation ->
                        Box(Modifier.padding(bottom = 12.dp).clickable { onOpen(conversation) }) {
                            Card {
                                Row(verticalAlignment = Alignment.CenterVertically) {
                                    val label = if (conversation.status == ConversationStatus.RESOLVED) cs.resolved else if (conversation.mode == ConversationMode.AI) cs.ai else cs.human
                                    Text(label, color = if (conversation.status == ConversationStatus.RESOLVED) palette.muted else accent.color, fontSize = 11.sp, fontWeight = FontWeight.SemiBold,
                                        modifier = Modifier.clip(RoundedCornerShape(7.dp)).background(accent.tint(0.08f)).padding(horizontal = 9.dp, vertical = 5.dp))
                                    Spacer(Modifier.weight(1f))
                                    Text(When.shortDate(conversation.createdAt), color = palette.muted, fontSize = 12.sp)
                                }
                                Text(conversation.preview.ifEmpty { cs.noMessages }, color = palette.ink, maxLines = 2)
                                Text(Conversations.channelLabel(conversation.channel), color = palette.muted, fontSize = 12.sp)
                            }
                        }
                    }
                    Spacer(Modifier.height(30.dp))
                }
            }
        }
    }
}

@Composable
private fun ActionTile(label: String, icon: androidx.compose.ui.graphics.vector.ImageVector, enabled: Boolean, modifier: Modifier, onClick: () -> Unit) {
    val accent = LocalAccent.current
    Column(
        modifier.height(84.dp).clip(RoundedCornerShape(14.dp)).background(accent.tint()).clickable(enabled = enabled, onClick = onClick).padding(12.dp)
            .then(if (enabled) Modifier else Modifier.alpha(0.4f)),
        horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Center,
    ) {
        Icon(icon, null, tint = accent.color, modifier = Modifier.size(22.dp))
        Text(label, color = accent.color, fontSize = 13.sp, fontWeight = FontWeight.SemiBold, textAlign = TextAlign.Center, modifier = Modifier.padding(top = 6.dp))
    }
}

/** Create or edit a contact's name, phone, email and notes. */
@Composable
private fun ContactEditor(contact: Contact?, busy: Boolean, serverError: String?, onSave: (ContactUpdate) -> Unit) {
    val cs = ContactsStrings.current
    val palette = LocalAccent.current.palette
    var name by remember { mutableStateOf(contact?.name ?: "") }
    var phone by remember { mutableStateOf((contact?.phone ?: "").filter { it.isDigit() }) }
    var email by remember { mutableStateOf(contact?.email ?: "") }
    var notes by remember { mutableStateOf(contact?.notes ?: "") }
    var error by remember { mutableStateOf<String?>(null) }
    Column(Modifier.verticalScroll(rememberScrollState()).padding(22.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        FieldLabel(cs.name)
        FormTextField(name, { name = it }, enabled = !busy)
        FieldLabel(cs.phone)
        PhoneField(phone, enabled = !busy, searchPlaceholder = cs.search) { phone = it }
        FieldLabel(cs.email)
        FormTextField(email, { email = it }, enabled = !busy, keyboard = KeyboardType.Email)
        FieldLabel(cs.notes)
        FormTextField(notes, { notes = it }, multiline = true, enabled = !busy)
        Text(cs.notesHint, color = palette.muted, fontSize = 12.sp)
        (error ?: serverError)?.let { Text(it, color = palette.danger) }
        Spacer(Modifier.height(14.dp))
        PrimaryButton(cs.save, busy = busy) {
            val digits = phone.filter { it.isDigit() }
            val trimmedPhone = phone.trim()
            // Existing web contacts can have no phone; editing notes must still work.
            if ((contact == null || !contact.phone.isNullOrEmpty() || trimmedPhone.isNotEmpty()) && (digits.length < 7 || digits.length > 15)) { error = cs.invalidPhone; return@PrimaryButton }
            val trimmedEmail = email.trim()
            if (trimmedEmail.isNotEmpty() && !Regex("^[^\\s@]+@[^\\s@]+\\.[^\\s@]+$").matches(trimmedEmail)) { error = cs.invalidEmail; return@PrimaryButton }
            error = null
            onSave(ContactUpdate(name.trim(), trimmedPhone.ifEmpty { null }, trimmedEmail.ifEmpty { null }, clearEmail = trimmedEmail.isEmpty(), notes = notes.trim()))
        }
    }
}

/** Pick which of the workspace's tags this contact carries. */
@Composable
private fun ContactTagsPicker(model: AppModel, contact: Contact, onSaved: (Contact) -> Unit) {
    val cs = ContactsStrings.current
    val palette = LocalAccent.current.palette
    val session = model.session ?: return
    val server = model.server
    var all by remember { mutableStateOf<List<ContactTag>>(emptyList()) }
    var chosen by remember { mutableStateOf(contact.tags?.map { it.id }?.toSet() ?: emptySet()) }
    var loading by remember { mutableStateOf(true) }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    val scope = rememberCoroutineScope()
    LaunchedEffect(Unit) { all = runCatching { PortalApi.tags(server, session) }.getOrDefault(emptyList()); loading = false }
    Column(Modifier.verticalScroll(rememberScrollState()).padding(22.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        if (loading) ContactsSkeleton(Strings.current.inbox.loading, 4)
        else if (all.isEmpty()) Text(cs.noTagsDefined, color = palette.muted)
        all.forEach { tag -> ChoiceRow(tag.name, null, tag.id in chosen, checkbox = true, enabled = !busy) { chosen = if (tag.id in chosen) chosen - tag.id else chosen + tag.id } }
        error?.let { Text(it, color = palette.danger) }
        Spacer(Modifier.height(12.dp))
        PrimaryButton(cs.done, busy = busy, enabled = !loading) {
            scope.launch {
                busy = true; error = null
                try { onSaved(PortalApi.setContactTags(server, session, contact.id, chosen.toList())) }
                catch (f: ApiException) { if (f.isUnauthorized) model.expireSession(); error = f.message } catch (f: Exception) { error = cs.saveFailed }
                busy = false
            }
        }
    }
}

/** Reaching out first: a free message on the bridge. Approved templates on WhatsApp Business stay on the web for now. */
@Composable
private fun StartConversation(model: AppModel, contact: Contact, channels: List<PortalChannel>, history: List<Conversation>, onOpen: (Conversation) -> Unit) {
    val cs = ContactsStrings.current
    val accent = LocalAccent.current
    val palette = accent.palette
    val session = model.session ?: return
    val server = model.server
    var channel by remember { mutableStateOf(channels.firstOrNull()?.channel ?: "") }
    var message by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    val scope = rememberCoroutineScope()
    val approved = channel == "whatsapp_cloud"
    val existing = history.firstOrNull { it.status == ConversationStatus.OPEN && it.channel == channel }
    Column(Modifier.verticalScroll(rememberScrollState()).padding(22.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        FieldLabel(cs.chooseLine)
        channels.forEach { line ->
            ChoiceRow(if (line.channel == "whatsapp_cloud") "WhatsApp Business" else "WhatsApp", listOfNotNull(line.displayName, line.phoneNumber).filter { it.isNotEmpty() }.joinToString(" · "), channel == line.channel, enabled = !busy) { channel = line.channel }
        }
        when {
            existing != null -> {
                Text(cs.existing, color = palette.muted, fontSize = 13.sp)
                Text(cs.open, color = accent.color, fontWeight = FontWeight.SemiBold, modifier = Modifier.clickable { onOpen(existing) }.padding(vertical = 10.dp))
            }
            approved -> { Text(cs.templateHint, color = palette.muted, fontSize = 13.sp); Text(cs.templatesWebOnly, color = palette.muted, fontSize = 13.sp) }
            else -> {
                Text(cs.startHint, color = palette.muted, fontSize = 13.sp)
                FieldLabel(cs.message)
                FormTextField(message, { message = it }, multiline = true, enabled = !busy)
                error?.let { Text(it, color = palette.danger) }
                Spacer(Modifier.height(12.dp))
                PrimaryButton(cs.send, enabled = message.isNotBlank(), busy = busy) {
                    scope.launch {
                        busy = true; error = null
                        try { onOpen(PortalApi.startWhatsAppConversation(server, session, contact.id, message.trim()).summary) }
                        catch (f: ApiException) { if (f.isUnauthorized) model.expireSession(); error = f.message } catch (f: Exception) { error = cs.sendFailed }
                        busy = false
                    }
                }
            }
        }
    }
}
