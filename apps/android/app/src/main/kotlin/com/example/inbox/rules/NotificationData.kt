package com.example.inbox.rules

/**
 * Delivery adapters may normalize their native envelope at this boundary.
 *
 * A publisher whose notification service wraps the payload replaces this one
 * file in their build; the rest of the app only ever sees a flat map.
 */
object NotificationData {
    fun normalize(data: Map<String, String>): Map<String, Any?> = data
}
