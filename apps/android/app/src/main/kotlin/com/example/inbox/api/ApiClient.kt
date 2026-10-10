package com.example.inbox.api

import com.example.inbox.localization.Strings
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.KSerializer
import kotlinx.serialization.builtins.serializer
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonNamingStrategy
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive

/** A failed call: the server's message when it gave one, and the status. */
class ApiException(message: String, val status: Int) : IOException(message) {
    val isUnauthorized: Boolean get() = status == 401
}

/**
 * Talks to the server this session was opened against.
 *
 * The server is not baked in: a person signs in by typing the address of the
 * instance their agency runs, so every call takes the base URL from the stored
 * session. Sign-in returns a token that is sent as a bearer credential from
 * then on. Nothing but the platform's own HTTP stack is involved.
 */
object ApiClient {
    @OptIn(kotlinx.serialization.ExperimentalSerializationApi::class)
    val json: Json = Json {
        ignoreUnknownKeys = true
        explicitNulls = false
        coerceInputValues = true
        namingStrategy = JsonNamingStrategy.SnakeCase
    }

    private const val TIMEOUT_MS = 30_000

    /** The app closes this gate while permission or session refresh is pending. */
    private val access = HashMap<String, Boolean>()

    @Synchronized
    fun setSessionAccess(session: Session, allowed: Boolean) { access[session.token] = allowed }

    @Synchronized
    private fun requireSessionAccess(token: String?) {
        if (token != null && access[token] == false) {
            throw ApiException(com.example.inbox.localization.PrivacyStrings.current.permissionRequired, 428)
        }
    }

    /** Accepts what a person actually types: "10.0.0.4:8000", "example.com", a full URL. */
    fun normalizeServerUrl(input: String): String {
        var value = input.trim()
        while (value.endsWith("/")) value = value.dropLast(1)
        if (value.isEmpty()) return ""
        if (!Regex("^https?://", RegexOption.IGNORE_CASE).containsMatchIn(value)) {
            val isLocal = Regex("^(localhost|127\\.0\\.0\\.1|10\\.0\\.2\\.2|10\\.|192\\.168\\.|172\\.(1[6-9]|2\\d|3[01])\\.)", RegexOption.IGNORE_CASE).containsMatchIn(value)
            value = (if (isLocal) "http" else "https") + "://" + value
        }
        if (value.endsWith("/api")) value = value.dropLast(4)
        return value
    }

    fun portalPath(session: Session, path: String): String = "/portal/${encodePathComponent(session.portalSlug)}$path"

    fun encodePathComponent(value: String): String = URLEncoder.encode(value, "UTF-8").replace("+", "%20")

    /** API failures are parsed once: FastAPI's `detail` as a string or a list of messages. */
    private fun failure(status: Int, body: String, fallback: String): ApiException {
        var message = fallback
        runCatching {
            val detail = json.parseToJsonElement(body).jsonObject["detail"]
            when {
                detail == null -> {}
                detail is JsonObject -> {}
                detail.toString().startsWith("[") -> detail.jsonArray.firstOrNull()?.jsonObject?.get("msg")?.jsonPrimitive?.content?.let { message = it }
                else -> message = detail.jsonPrimitive.content
            }
        }
        return ApiException(message, status)
    }

    private suspend fun exchange(url: URL, method: String, body: String?, token: String?): Pair<Int, String> = withContext(Dispatchers.IO) {
        val connection = url.openConnection() as HttpURLConnection
        try {
            connection.requestMethod = method
            connection.connectTimeout = TIMEOUT_MS
            connection.readTimeout = TIMEOUT_MS
            connection.instanceFollowRedirects = false
            connection.useCaches = false
            connection.setRequestProperty("Accept", "application/json")
            if (token != null) connection.setRequestProperty("Authorization", "Bearer $token")
            if (body != null) {
                connection.doOutput = true
                connection.setRequestProperty("Content-Type", "application/json")
                connection.outputStream.use { it.write(body.toByteArray()) }
            }
            val status = connection.responseCode
            val stream = if (status in 200..299) connection.inputStream else connection.errorStream
            val text = stream?.bufferedReader()?.use { it.readText() } ?: ""
            status to text
        } finally {
            connection.disconnect()
        }
    }

    private fun url(server: String, path: String): URL = try {
        URL("$server/api$path")
    } catch (error: Exception) {
        throw ApiException(Strings.current.signIn.invalidServer, 0)
    }

    private suspend fun <T> perform(url: URL, method: String, body: String?, token: String?, serializer: KSerializer<T>?): T? {
        val fallback = Strings.current.errors.generic
        val (status, text) = try {
            exchange(url, method, body, token)
        } catch (error: CancellationException) {
            throw error
        } catch (error: ApiException) {
            throw error
        } catch (error: Exception) {
            throw ApiException(Strings.current.errors.unreachable, 0)
        }
        if (status !in 200..299) throw failure(status, text, fallback)
        if (serializer == null) return null
        if (status == 204 || text.isEmpty()) throw ApiException(fallback, status)
        return try {
            json.decodeFromString(serializer, text)
        } catch (error: Exception) {
            throw ApiException(fallback, status)
        }
    }

    suspend fun <T> request(server: String, path: String, serializer: KSerializer<T>, method: String = "GET", body: String? = null, token: String? = null): T {
        val gateExempt = path == "/mobile/session" || (path.startsWith("/mobile/devices/") && method == "DELETE")
        if (!gateExempt) requireSessionAccess(token)
        return perform(url(server, path), method, body, token, serializer)!!
    }

    suspend fun requestVoid(server: String, path: String, method: String, body: String? = null, token: String? = null) {
        requireSessionAccess(token)
        perform(url(server, path), method, body, token, null as KSerializer<Unit>?)
    }

    /** A request to an absolute address, for endpoints outside a workspace's `/api`. */
    suspend fun <T> request(url: URL, serializer: KSerializer<T>, method: String = "GET", body: String? = null): T =
        perform(url, method, body, null, serializer)!!

    inline fun <reified T> encode(value: T): String = json.encodeToString(kotlinx.serialization.serializer<T>(), value)

    @Suppress("unused")
    private val unitSerializer = Unit.serializer()
}
