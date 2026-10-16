package com.example.inbox.ui

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
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.systemBarsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.inbox.AppModel
import com.example.inbox.Brand
import com.example.inbox.R
import com.example.inbox.api.ApiClient
import com.example.inbox.api.ApiException
import com.example.inbox.api.HostedAccount
import com.example.inbox.api.PortalApi
import com.example.inbox.localization.PrivacyStrings
import com.example.inbox.localization.Strings
import kotlinx.coroutines.launch

/**
 * Where the session comes from.
 *
 * A build with an account directory accepts an e-mail and password; the
 * directory answers with the account's own server, or with several accounts
 * when the same person works for more than one business. "Change server" is
 * for a self-hosted core, where the address is typed and the sign-in goes
 * straight to it.
 */
@Composable
fun SignInScreen(model: AppModel) {
    val s = Strings.current.signIn
    val p = PrivacyStrings.current
    val accent = LocalAccent.current
    val palette = accent.palette
    val scope = rememberCoroutineScope()
    val uriHandler = LocalUriHandler.current
    val context = LocalContext.current

    var serverPage by remember { mutableStateOf(Brand.hosted == null && Brand.defaultServer.isEmpty()) }
    var server by remember { mutableStateOf(Brand.defaultServer) }
    var draft by remember { mutableStateOf(Brand.defaultServer.removePrefix("https://")) }
    var hosted by remember { mutableStateOf(Brand.hosted != null) }
    var email by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    var accounts by remember { mutableStateOf<List<HostedAccount>>(emptyList()) }
    var forgot by remember { mutableStateOf(false) }

    fun finish(account: HostedAccount) {
        try {
            model.signedIn(account.server, account.session)
            accounts = emptyList()
        } catch (failure: Exception) {
            error = s.failed
        }
    }

    fun submit() {
        val address = email.trim()
        if (address.isEmpty() || password.isEmpty() || busy) return
        busy = true
        error = null
        scope.launch {
            try {
                if (hosted) {
                    val directory = Brand.hostedSignInUrl
                    if (directory == null) {
                        // Without an account directory, ask for the server address.
                        serverPage = true
                    } else {
                        val found = try {
                            PortalApi.hostedSignIn(directory, address, password)
                        } catch (failure: ApiException) {
                            // The directory is not answering: a service problem, not a wrong address.
                            if (failure.status == 404) throw ApiException(s.failed, 503) else throw failure
                        }
                        val first = found.firstOrNull() ?: throw ApiException(s.incorrectCredentials, 401)
                        if (found.size == 1) finish(first) else accounts = found
                    }
                } else {
                    val session = PortalApi.signIn(server, address, password)
                    model.signedIn(server, session)
                }
            } catch (failure: ApiException) {
                error = when (failure.status) {
                    404 -> s.workspaceUnavailable
                    401 -> s.incorrectCredentials
                    else -> failure.message ?: s.failed
                }
            } catch (failure: Exception) {
                error = s.failed
            } finally {
                busy = false
            }
        }
    }

    Column(
        Modifier.fillMaxSize().background(palette.canvas).systemBarsPadding().imePadding().verticalScroll(rememberScrollState()).padding(horizontal = 26.dp),
    ) {
        Spacer(Modifier.height(72.dp))
        Box(Modifier.size(52.dp).clip(RoundedCornerShape(14.dp)).background(palette.surface), contentAlignment = Alignment.Center) {
            androidx.compose.foundation.Image(
                painter = androidx.compose.ui.res.painterResource(R.drawable.brand_logo),
                contentDescription = Brand.name, modifier = Modifier.size(40.dp),
            )
        }
        Spacer(Modifier.height(28.dp))
        if (serverPage) {
            Text(s.serverTitle, color = palette.ink, fontSize = 30.sp, fontWeight = FontWeight.Bold)
            Text(s.serverHint, color = palette.muted, fontSize = 17.sp, modifier = Modifier.padding(top = 8.dp, bottom = 28.dp))
            LabeledField(s.serverLabel, draft, s.serverPlaceholder, { draft = it }, keyboard = KeyboardType.Uri)
            Spacer(Modifier.height(20.dp))
            PrimaryButton(s.connect, enabled = ApiClient.normalizeServerUrl(draft).isNotEmpty()) {
                server = ApiClient.normalizeServerUrl(draft)
                hosted = false
                serverPage = false
                error = null
            }
            if (Brand.hosted != null) {
                Spacer(Modifier.height(28.dp))
                Text(
                    s.useHosted.replace("{name}", Brand.hosted!!.label), color = palette.muted, fontSize = 17.sp,
                    modifier = Modifier.fillMaxWidth().clickable { hosted = true; serverPage = false; error = null }.padding(12.dp),
                    textAlign = androidx.compose.ui.text.style.TextAlign.Center,
                )
            }
        } else {
            val connectedName = if (hosted) Brand.hosted?.label ?: Brand.name else runCatching { java.net.URL(server).host }.getOrNull() ?: server
            Text(s.title, color = palette.ink, fontSize = 30.sp, fontWeight = FontWeight.Bold)
            Text(s.connectedTo.replace("{name}", connectedName), color = palette.muted, fontSize = 17.sp, modifier = Modifier.padding(top = 8.dp, bottom = 28.dp))
            LabeledField(s.emailLabel, email, s.emailPlaceholder, { email = it }, keyboard = KeyboardType.Email, enabled = !busy)
            Spacer(Modifier.height(16.dp))
            LabeledField(s.passwordLabel, password, "••••••••", { password = it }, password = true, keyboard = KeyboardType.Password, enabled = !busy)
            Row(Modifier.fillMaxWidth().padding(top = 10.dp), horizontalArrangement = Arrangement.End) {
                Text(s.forgot, color = accent.color, fontSize = 16.sp, modifier = Modifier.clickable { forgot = true }.padding(4.dp))
            }
            if (error != null) Text(error!!, color = palette.danger, modifier = Modifier.padding(top = 8.dp))
            Spacer(Modifier.height(20.dp))
            PrimaryButton(s.submit, enabled = email.isNotBlank() && password.isNotEmpty(), busy = busy) { submit() }
            Spacer(Modifier.height(28.dp))
            Text(
                if (hosted || Brand.hosted == null) s.changeServer else s.useHosted.replace("{name}", Brand.hosted!!.label),
                color = palette.muted, fontSize = 17.sp,
                modifier = Modifier.fillMaxWidth().clickable {
                    if (hosted || Brand.hosted == null) serverPage = true else { hosted = true; error = null }
                }.padding(12.dp),
                textAlign = androidx.compose.ui.text.style.TextAlign.Center,
            )
        }
        Row(Modifier.fillMaxWidth().padding(top = 12.dp, bottom = 40.dp), horizontalArrangement = Arrangement.spacedBy(28.dp, Alignment.CenterHorizontally)) {
            Brand.privacyPolicyUrl?.let { url -> Text(p.policy, color = palette.muted, modifier = Modifier.clickable { uriHandler.openUri(url.toString()) }) }
            Brand.supportUrl?.let { url -> Text(p.support, color = palette.muted, modifier = Modifier.clickable { uriHandler.openUri(url.toString()) }) }
        }
    }

    if (forgot) {
        AlertDialog(
            onDismissRequest = { forgot = false },
            title = { Text(s.forgotTitle) }, text = { Text(s.forgotBody) },
            confirmButton = { TextButton({ forgot = false }) { Text(Strings.current.inbox.done) } },
        )
    }
    if (accounts.size > 1) {
        AlertDialog(
            onDismissRequest = { accounts = emptyList() },
            title = { Text(s.chooseAccount) },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(s.chooseAccountBody, color = palette.muted)
                    accounts.forEach { account ->
                        Row(
                            Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(palette.canvas).clickable { finish(account) }.padding(12.dp),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Avatar(account.session.branding.clientName, 36.dp, 12.dp, 15)
                            Spacer(Modifier.size(12.dp))
                            Column {
                                Text(account.session.branding.clientName, color = palette.ink, fontWeight = FontWeight.SemiBold)
                                Text(runCatching { java.net.URL(account.server).host }.getOrNull() ?: account.server, color = palette.muted, fontSize = 13.sp)
                            }
                        }
                    }
                }
            },
            confirmButton = {}, dismissButton = { TextButton({ accounts = emptyList() }) { Text(Strings.current.inbox.cancel) } },
        )
    }
    // The context is unused on purpose; it keeps the composable honest about where links open.
    context.hashCode()
}
