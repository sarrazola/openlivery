package com.example.inbox.push

import android.content.Intent

/** The tap that opened the app, kept until a signed-in session can act on it. */
object NotificationRouter {
    const val EXTRA_PREFIX = "notification."
    data class Tap(val identifier: String, val data: Map<String, String>)

    @Volatile var pending: Tap? = null; private set
    @Volatile var handler: (() -> Unit)? = null

    /** Reads the data a notification's content intent carried, if this intent came from one. */
    fun accept(intent: Intent?) {
        val extras = intent?.extras ?: return
        val data = extras.keySet().filter { it.startsWith(EXTRA_PREFIX) }.associate { it.removePrefix(EXTRA_PREFIX) to (extras.getString(it) ?: "") }
        if (data.isEmpty()) return
        pending = Tap(extras.getString("notification_tap_id") ?: data.hashCode().toString(), data)
        handler?.invoke()
    }

    fun clear() { pending = null }
}
