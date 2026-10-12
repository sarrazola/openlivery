package com.example.inbox

import android.app.Application
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.example.inbox.api.ApiClient
import com.example.inbox.api.ApiException
import com.example.inbox.api.Conversation
import com.example.inbox.api.PortalApi
import com.example.inbox.api.Session
import com.example.inbox.localization.Strings
import com.example.inbox.push.NotificationRouter
import com.example.inbox.push.PushSession
import com.example.inbox.rules.NotificationTarget
import com.example.inbox.storage.ConsentStore
import com.example.inbox.storage.SessionStore
import com.example.inbox.storage.StoredSession
import kotlinx.coroutines.launch

/**
 * The root state machine: which screen is up, which session it runs on, and
 * the privacy gate that sits between them.
 */
class AppModel(application: Application) : AndroidViewModel(application) {
    enum class Screen { LOADING, SIGN_IN, RECONNECT, PRIVACY, MAIN }
    enum class Tab { INBOX, CONTACTS, REPORTS, SETTINGS }

    data class AlertContent(val title: String, val message: String? = null)

    var screen by mutableStateOf(Screen.LOADING); private set
    var server by mutableStateOf(""); private set
    var session by mutableStateOf<Session?>(null); private set
    var privacyApproved by mutableStateOf(false); private set
    var privacyChecking by mutableStateOf(false); private set
    var signOutBusy by mutableStateOf(false); private set
    var tab by mutableStateOf(Tab.INBOX)
    var inboxPath by mutableStateOf<List<Conversation>>(emptyList())
    var contactsPath by mutableStateOf<List<Conversation>>(emptyList())
    var alert by mutableStateOf<AlertContent?>(null)

    private var authGeneration = 0
    private var signingOut = false
    private var wasBackgrounded = false
    private var pushSession: PushSession? = null
    private var pushKey: String? = null
    private var handledNotification = ""
    private val context get() = getApplication<Application>()

    init {
        NotificationRouter.handler = { processPendingNotification() }
    }

    // MARK: Session lifecycle

    fun restore() {
        authGeneration += 1
        val generation = authGeneration
        privacyApproved = false
        screen = Screen.LOADING
        val stored = SessionStore.load(context)
        if (stored == null) {
            screen = Screen.SIGN_IN
            return
        }
        viewModelScope.launch {
            try {
                val next = PortalApi.resumeSession(stored.server, stored.token)
                if (generation != authGeneration) return@launch
                ApiClient.setSessionAccess(next, false)
                val approved = ConsentStore.hasConsent(context, stored.server, next)
                ApiClient.setSessionAccess(next, approved)
                server = stored.server
                session = next
                privacyApproved = approved
                privacyChecking = false
                screen = if (approved) Screen.MAIN else Screen.PRIVACY
                syncPush()
                processPendingNotification()
            } catch (error: ApiException) {
                if (generation != authGeneration) return@launch
                if (error.isUnauthorized) {
                    SessionStore.clear(context)
                    screen = Screen.SIGN_IN
                } else {
                    // An offline launch must not erase a valid login.
                    screen = Screen.RECONNECT
                }
            } catch (error: Exception) {
                if (generation != authGeneration) return@launch
                screen = Screen.RECONNECT
            }
        }
    }

    fun signedIn(base: String, next: Session) {
        ApiClient.setSessionAccess(next, false)
        SessionStore.store(context, StoredSession(base, next.token))
        val approved = ConsentStore.hasConsent(context, base, next)
        authGeneration += 1
        server = base
        session = next
        ApiClient.setSessionAccess(next, approved)
        privacyApproved = approved
        privacyChecking = false
        tab = Tab.INBOX
        inboxPath = emptyList()
        contactsPath = emptyList()
        screen = if (approved) Screen.MAIN else Screen.PRIVACY
        syncPush()
    }

    fun acceptPrivacy() {
        val current = session ?: return
        val generation = authGeneration
        ConsentStore.accept(context, server, current)
        if (generation != authGeneration) return
        ApiClient.setSessionAccess(current, true)
        privacyApproved = true
        screen = Screen.MAIN
        syncPush()
        processPendingNotification()
    }

    fun withdrawPrivacy() {
        ConsentStore.withdraw(context)
        session?.let { ApiClient.setSessionAccess(it, false) }
        privacyApproved = false
        signOut()
    }

    fun showPrivacy() { screen = Screen.PRIVACY }
    fun leavePrivacy() { if (privacyApproved) screen = Screen.MAIN }

    fun signOut() {
        if (signingOut) return
        signingOut = true
        authGeneration += 1
        val previous = session
        previous?.let { ApiClient.setSessionAccess(it, false) }
        signOutBusy = true
        viewModelScope.launch {
        try {
            // A new account must not register the same native token before the old registration is released.
            stopPush()
            SessionStore.clear(context)
            authGeneration += 1
            session = null
            privacyApproved = false
            privacyChecking = false
            server = ""
            inboxPath = emptyList()
            contactsPath = emptyList()
            tab = Tab.INBOX
            screen = Screen.SIGN_IN
        } catch (error: Exception) {
            if (previous != null) {
                val approved = ConsentStore.hasConsent(context, server, previous)
                ApiClient.setSessionAccess(previous, approved)
                privacyApproved = approved
            }
            alert = AlertContent(Strings.current.errors.generic, error.message)
        }
        signingOut = false
        signOutBusy = false
        }
    }

    fun expireSession() { signOut() }

    // MARK: Foreground and background

    fun lifecycleChanged(foreground: Boolean) {
        val current = session ?: return
        if (foreground && !wasBackgrounded) return
        wasBackgrounded = !foreground
        ApiClient.setSessionAccess(current, false)
        privacyChecking = true
        authGeneration += 1
        if (!foreground) return
        // A consented session comes straight back on screen; the server's answer
        // only matters if it withdraws it or changes the disclosure.
        val keepShowing = privacyApproved && screen == Screen.MAIN
        if (keepShowing) {
            ApiClient.setSessionAccess(current, true)
            privacyChecking = false
        }
        val generation = authGeneration
        viewModelScope.launch {
            try {
                val next = PortalApi.resumeSession(server, current.token)
                if (generation != authGeneration || signingOut) return@launch
                val approved = ConsentStore.hasConsent(context, server, next)
                ApiClient.setSessionAccess(next, approved)
                if (!approved) ApiClient.setSessionAccess(current, false)
                session = next
                privacyApproved = approved
                privacyChecking = false
                if (!approved) screen = Screen.PRIVACY
                else if (screen == Screen.RECONNECT) screen = Screen.MAIN
                syncPush()
                processPendingNotification()
            } catch (error: ApiException) {
                if (generation != authGeneration) return@launch
                if (error.isUnauthorized) expireSession() else { privacyChecking = false; if (!keepShowing) screen = Screen.RECONNECT }
            } catch (error: Exception) {
                if (generation != authGeneration) return@launch
                privacyChecking = false
                if (!keepShowing) screen = Screen.RECONNECT
            }
        }
    }

    // MARK: Navigation

    fun openConversation(conversation: Conversation) {
        when (tab) {
            Tab.CONTACTS -> contactsPath = contactsPath + conversation
            Tab.INBOX -> inboxPath = inboxPath + conversation
            Tab.REPORTS, Tab.SETTINGS -> { tab = Tab.INBOX; inboxPath = inboxPath + conversation }
        }
    }

    fun back() {
        when (tab) {
            Tab.CONTACTS -> if (contactsPath.isNotEmpty()) contactsPath = contactsPath.dropLast(1)
            else -> if (inboxPath.isNotEmpty()) inboxPath = inboxPath.dropLast(1)
        }
    }

    // MARK: Notifications

    private fun processPendingNotification() {
        val tap = NotificationRouter.pending ?: return
        val current = session ?: return
        if (!privacyApproved || privacyChecking || signOutBusy || screen != Screen.MAIN) return
        if (handledNotification == tap.identifier) return
        handledNotification = tap.identifier
        val id = NotificationTarget.conversationId(tap.data, current.clientId)
        if (id == null) { NotificationRouter.clear(); return }
        val generation = authGeneration
        viewModelScope.launch {
            try {
                val detail = PortalApi.conversation(server, current, id)
                if (generation != authGeneration) return@launch
                tab = Tab.INBOX
                inboxPath = listOf(detail.summary)
            } catch (error: ApiException) {
                if (error.isUnauthorized) expireSession() else alert = AlertContent(Strings.current.inbox.notificationUnavailable, error.message)
            } catch (error: Exception) {
                alert = AlertContent(Strings.current.inbox.notificationUnavailable, error.message)
            } finally {
                NotificationRouter.clear()
            }
        }
    }

    // MARK: Push

    private fun syncPush() {
        val current = session
        if (current == null || !privacyApproved) { viewModelScope.launch { stopPush() }; return }
        val key = "$server|${current.token}|${current.push.enabled}|${current.push.provider}"
        if (key == pushKey) return
        val base = server
        viewModelScope.launch {
            stopPush()
            if (session?.token != current.token || !privacyApproved) return@launch
            pushKey = key
            val next = PushSession(base, current, viewModelScope)
            pushSession = next
            next.start()
        }
    }

    private suspend fun stopPush() {
        val current = pushSession ?: return
        pushSession = null
        pushKey = null
        current.stop()
    }

    /** Whether a consented session wants the notification permission asked for. */
    val wantsNotifications: Boolean get() = session?.push?.enabled == true && privacyApproved && screen == Screen.MAIN
}
