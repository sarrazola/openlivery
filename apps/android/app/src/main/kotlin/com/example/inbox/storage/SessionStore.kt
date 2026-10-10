package com.example.inbox.storage

import android.content.Context
import android.content.SharedPreferences
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json

/** Bearer credentials, kept in a file encrypted with a key the hardware keystore holds. */
@Serializable
data class StoredSession(val server: String, val token: String)

/** The encrypted preferences every secret of this app lives in: the credential and the consent fingerprint. */
object SecureStore {
    @Volatile private var preferences: SharedPreferences? = null

    fun open(context: Context): SharedPreferences {
        preferences?.let { return it }
        synchronized(this) {
            preferences?.let { return it }
            val key = MasterKey.Builder(context.applicationContext).setKeyScheme(MasterKey.KeyScheme.AES256_GCM).build()
            val created = EncryptedSharedPreferences.create(
                context.applicationContext, "inbox.secure", key,
                EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV, EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM,
            )
            preferences = created
            return created
        }
    }
}

object SessionStore {
    private const val KEY = "inbox.session.v1"
    private val json = Json { ignoreUnknownKeys = true }

    fun load(context: Context): StoredSession? {
        val raw = SecureStore.open(context).getString(KEY, null) ?: return null
        val session = runCatching { json.decodeFromString(StoredSession.serializer(), raw) }.getOrNull() ?: return null
        if (session.token.isEmpty()) return null
        val url = runCatching { java.net.URL(session.server) }.getOrNull() ?: return null
        if (url.protocol !in listOf("http", "https") || url.userInfo != null) return null
        return session
    }

    /** Never fall back to plaintext if the device cannot persist a credential. */
    fun store(context: Context, session: StoredSession) {
        val ok = SecureStore.open(context).edit().putString(KEY, json.encodeToString(StoredSession.serializer(), session)).commit()
        if (!ok) throw IllegalStateException("credential store refused the write")
    }

    fun clear(context: Context) {
        SecureStore.open(context).edit().remove(KEY).commit()
    }
}
