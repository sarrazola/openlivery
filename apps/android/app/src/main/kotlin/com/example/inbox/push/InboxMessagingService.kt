package com.example.inbox.push

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat
import com.example.inbox.MainActivity
import com.example.inbox.R
import com.example.inbox.localization.Strings
import com.example.inbox.rules.NotificationData
import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage

/** Shows what the channel delivers and hands a tap to the app with the payload intact. */
class InboxMessagingService : FirebaseMessagingService() {
    override fun onNewToken(token: String) {
        PushRegistrar.onToken?.invoke(token)
    }

    override fun onMessageReceived(message: RemoteMessage) {
        val data = message.data
        val flat = NotificationData.normalize(data)
        val title = message.notification?.title ?: flat["title"] as? String ?: data["title"] ?: Strings.current.inbox.title
        val body = message.notification?.body ?: flat["body"] as? String ?: data["alert"] ?: data["body"] ?: ""
        if (Build.VERSION.SDK_INT >= 33 && ContextCompat.checkSelfPermission(this, android.Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) return
        val manager = getSystemService(NotificationManager::class.java)
        if (Build.VERSION.SDK_INT >= 26) manager.createNotificationChannel(NotificationChannel(CHANNEL, Strings.current.inbox.title, NotificationManager.IMPORTANCE_HIGH))
        val intent = Intent(this, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP)
        data.forEach { (key, value) -> intent.putExtra(NotificationRouter.EXTRA_PREFIX + key, value) }
        intent.putExtra("notification_tap_id", message.messageId ?: System.currentTimeMillis().toString())
        val pending = PendingIntent.getActivity(this, (message.messageId ?: "").hashCode(), intent, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        val notification = NotificationCompat.Builder(this, CHANNEL)
            .setSmallIcon(R.drawable.ic_notification)
            .setContentTitle(title)
            .setContentText(body)
            .setStyle(NotificationCompat.BigTextStyle().bigText(body))
            .setAutoCancel(true)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setContentIntent(pending)
            .build()
        manager.notify((flat["conversation_id"] as? String ?: message.messageId ?: "").hashCode(), notification)
    }

    companion object { const val CHANNEL = "messages" }
}
