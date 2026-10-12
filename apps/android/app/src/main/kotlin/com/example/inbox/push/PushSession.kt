package com.example.inbox.push

import com.example.inbox.api.DeviceRegistration
import com.example.inbox.api.PortalApi
import com.example.inbox.api.Session
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch

/**
 * One signed-in session's registration, disposed fully before another account
 * registers this install's native token.
 */
class PushSession(private val server: String, private val session: Session, private val scope: CoroutineScope) {
    private val registered = HashSet<String>()
    private var job: Job? = null
    @Volatile private var active = true

    fun start() {
        if (!session.push.enabled) { PushRegistrar.status = "server does not notify (provider ${session.push.provider})"; return }
        if (!PushRegistrar.configured) return
        PushRegistrar.onToken = { token -> if (active) scope.launch { register(token) } }
        job = scope.launch {
            val token = PushRegistrar.nativeToken() ?: return@launch
            if (active) register(token)
        }
    }

    private suspend fun register(token: String) {
        try {
            val result = PortalApi.registerDevice(server, session, DeviceRegistration(token, session.push.provider, PLATFORM))
            if (active) synchronized(registered) { registered.add(token) }
            PushRegistrar.status = "registered with the server (${result.provider}, enabled=${result.registered})"
            android.util.Log.i("push", "registered with the server: provider=${result.provider} registered=${result.registered}")
        } catch (error: Exception) {
            // A person can revoke permission at any time; not worth an error on screen.
            PushRegistrar.status = "registration failed: ${error.message}"
            android.util.Log.w("push", "registration failed: ${error.message}")
        }
    }

    /** Release this install on sign-out so a shared phone stops ringing. */
    suspend fun stop() {
        active = false
        PushRegistrar.onToken = null
        job?.cancel()
        val tokens = synchronized(registered) { registered.toList().also { registered.clear() } }
        for (token in tokens) {
            // Signing out locally matters more than tidying the server's registry.
            runCatching { PortalApi.forgetDevice(server, session, token) }
        }
    }

    companion object { const val PLATFORM = "android" }
}
