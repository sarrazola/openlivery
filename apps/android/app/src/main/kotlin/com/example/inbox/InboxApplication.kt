package com.example.inbox

import android.app.Application
import com.example.inbox.media.AttachmentCache

class InboxApplication : Application() {
    override fun onCreate() {
        super.onCreate()
        AttachmentCache.install(this)
    }
}
