package com.example.inbox

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.viewModels
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import android.content.Intent
import android.os.Build
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import com.example.inbox.localization.Strings
import com.example.inbox.push.NotificationRouter
import com.example.inbox.push.PushRegistrar
import com.example.inbox.ui.Accent
import com.example.inbox.ui.LocalAccent
import com.example.inbox.ui.MainTabs
import com.example.inbox.ui.Palette
import com.example.inbox.ui.PrimaryButton
import com.example.inbox.ui.PrivacyScreen
import com.example.inbox.ui.SignInScreen

class MainActivity : ComponentActivity() {
    private val model: AppModel by viewModels()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        PushRegistrar.initialize(applicationContext)
        NotificationRouter.accept(intent)
        setContent { RootView(model) }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        NotificationRouter.accept(intent)
    }
}

/** Picks the screen the model says is up and keeps the sign-out veil on top. */
@Composable
fun RootView(model: AppModel) {
    val dark = isSystemInDarkTheme()
    val palette = Palette.current(dark)
    var foreground by remember { mutableStateOf(true) }
    val lifecycleOwner = LocalLifecycleOwner.current

    LaunchedEffect(Unit) { model.restore() }
    // The permission is asked only once the server has said it can notify, so a prompt never leads to nothing.
    val notificationPermission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) {}
    LaunchedEffect(model.wantsNotifications) {
        if (model.wantsNotifications && PushRegistrar.configured && Build.VERSION.SDK_INT >= 33) notificationPermission.launch(android.Manifest.permission.POST_NOTIFICATIONS)
    }
    DisposableEffect(lifecycleOwner) {
        val observer = LifecycleEventObserver { _, event ->
            when (event) {
                Lifecycle.Event.ON_STOP -> { foreground = false; model.lifecycleChanged(false) }
                Lifecycle.Event.ON_START -> { foreground = true; model.lifecycleChanged(true) }
                else -> {}
            }
        }
        lifecycleOwner.lifecycle.addObserver(observer)
        onDispose { lifecycleOwner.lifecycle.removeObserver(observer) }
    }

    val brandHex = model.session?.branding?.brandColor?.takeIf { it.length == 7 } ?: Brand.primaryColorHex
    val accent = remember(brandHex, dark) { Accent(brandHex, dark) }
    val scheme = if (dark) darkColorScheme(primary = accent.color, surface = palette.surface, background = palette.canvas)
    else lightColorScheme(primary = accent.color, surface = palette.surface, background = palette.canvas)

    MaterialTheme(colorScheme = scheme) {
        CompositionLocalProvider(LocalAccent provides accent) {
            Box(Modifier.fillMaxSize().background(palette.canvas)) {
                when {
                    model.screen == AppModel.Screen.LOADING || model.privacyChecking ->
                        Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) { CircularProgressIndicator(color = palette.muted) }
                    model.screen == AppModel.Screen.RECONNECT -> ReconnectView(model)
                    model.screen == AppModel.Screen.SIGN_IN || model.session == null -> SignInScreen(model)
                    !model.privacyApproved || model.screen == AppModel.Screen.PRIVACY ->
                        PrivacyScreen(model, model.session!!, model.server, model.privacyApproved)
                    else -> MainTabs(model, foreground)
                }
                if (model.signOutBusy) {
                    Box(Modifier.fillMaxSize().background(palette.canvas), contentAlignment = Alignment.Center) { CircularProgressIndicator(color = palette.muted) }
                }
            }
            model.alert?.let { alert ->
                AlertDialog(
                    onDismissRequest = { model.alert = null },
                    title = { Text(alert.title) }, text = alert.message?.let { { Text(it) } },
                    confirmButton = { TextButton({ model.alert = null }) { Text(Strings.current.inbox.done) } },
                )
            }
        }
    }
}

@Composable
private fun ReconnectView(model: AppModel) {
    val s = Strings.current.inbox
    val palette = LocalAccent.current.palette
    Column(Modifier.fillMaxSize().padding(30.dp), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = androidx.compose.foundation.layout.Arrangement.Center) {
        Text(s.reconnectTitle, color = palette.ink, fontSize = 24.sp, fontWeight = FontWeight.Bold)
        Text(s.reconnectBody, color = palette.muted, modifier = Modifier.padding(top = 8.dp, bottom = 24.dp), textAlign = androidx.compose.ui.text.style.TextAlign.Center)
        PrimaryButton(s.retry) { model.restore() }
        Text(s.signOut, color = palette.muted, modifier = Modifier.padding(top = 16.dp).clickable { model.signOut() })
    }
}
