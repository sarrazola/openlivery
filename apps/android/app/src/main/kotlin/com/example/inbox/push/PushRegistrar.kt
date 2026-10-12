package com.example.inbox.push

import android.content.Context
import android.util.Log
import com.example.inbox.BuildConfig
import com.google.firebase.FirebaseApp
import com.google.firebase.FirebaseOptions
import com.google.firebase.messaging.FirebaseMessaging
import kotlinx.coroutines.tasks.await

/**
 * Registering this install for notifications, without choosing a provider.
 *
 * The app asks the platform's push channel for its native token and hands it to
 * the server, which delivers through whatever it was configured with. No push
 * vendor's SDK is involved. The channel itself is only initialised when the
 * brand carries its identifiers, so a self-hosted build without them registers
 * nothing and never asks for permission.
 *
 * Two rules this module exists to keep:
 *
 * 1. If the server says it cannot notify, ask for nothing.
 * 2. Never let any of this break the app: every failure here is swallowed.
 */
object PushRegistrar {
    private const val TAG = "push"

    val configured: Boolean = listOf(BuildConfig.BRAND_FCM_PROJECT_ID, BuildConfig.BRAND_FCM_APP_ID, BuildConfig.BRAND_FCM_API_KEY, BuildConfig.BRAND_FCM_SENDER_ID).all { it.isNotBlank() }

    @Volatile private var initialised = false
    /** What the last attempt found, for the settings screen. */
    @Volatile var status: String = if (configured) "channel not initialised" else "channel not configured"
    /** Called whenever the channel hands over a new token while a session is active. */
    @Volatile var onToken: ((String) -> Unit)? = null

    fun initialize(context: Context) {
        if (!configured || initialised) return
        try {
            if (FirebaseApp.getApps(context).isEmpty()) {
                val options = FirebaseOptions.Builder()
                    .setProjectId(BuildConfig.BRAND_FCM_PROJECT_ID)
                    .setApplicationId(BuildConfig.BRAND_FCM_APP_ID)
                    .setApiKey(BuildConfig.BRAND_FCM_API_KEY)
                    .setGcmSenderId(BuildConfig.BRAND_FCM_SENDER_ID)
                    .build()
                FirebaseApp.initializeApp(context, options)
            }
            initialised = true
            status = "channel ready"
        } catch (error: Exception) {
            status = "channel failed: ${error.message}"
            Log.w(TAG, "notification channel not initialised: ${error.message}")
        }
    }

    /** The native token, or nothing when the channel is off or unreachable. */
    suspend fun nativeToken(): String? {
        if (!configured || !initialised) return null
        return try { FirebaseMessaging.getInstance().token.await().also { status = "token obtained" } } catch (error: Exception) { status = "no token: ${error.message}"; Log.w(TAG, "no token: ${error.message}"); null }
    }
}
