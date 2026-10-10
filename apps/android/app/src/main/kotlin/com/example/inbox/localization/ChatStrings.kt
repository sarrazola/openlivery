package com.example.inbox.localization

import com.example.inbox.api.Message

/** Typed conversation copy, selected using the device language. */
class ChatStrings(
    val ai: String, val details: String, val close: String, val retry: String, val cancel: String, val save: String, val done: String,
    val open: String, val resolved: String, val resolve: String, val resolveTitle: String, val resolveHint: String, val resolvedHint: String,
    val resolveConfirm: String, val assignee: String, val unassigned: String, val team: String, val noTeam: String, val me: String,
    val agent: String, val visitor: String, val windowClosed: String, val windowHint: String, val socialBlocked: String, val socialWindowHint: String,
    val socialHumanOnly: String, val socialHumanHint: String, val unsupportedAttachment: String, val actions: String,
    val quote: String, val quoting: String, val cancelQuote: String, val unavailableQuote: String, val react: String, val removeReaction: String,
    val sent: String, val delivered: String, val read: String, val pending: String, val unknown: String, val failed: String, val someone: String,
    val newMessages: String, val latest: String, val updateFailed: String, val canned: String, val noCanned: String, val searchReplies: String,
    val file: String, val removeFile: String, val attachmentFailed: String, val attachmentRetry: String, val audioFailed: String, val openFile: String,
    val viewImage: String, val caption: String, val attached: String, val pickFailed: String, val recordFailed: String,
    val recordAudio: String, val audioReady: String, val micUnavailable: String, val recordingTooShort: String,
    val events: Map<String, String>,
) {
    fun delivery(label: String): String = when (label) {
        "sent" -> sent; "delivered" -> delivered; "read" -> read; "pending" -> pending; "failed" -> failed; else -> unknown
    }

    /** Activity rows carry an event name and its variables; the actor is the sender. */
    fun activityLabel(message: Message): String {
        val event = message.activityValue("event") ?: ""
        val template = events[event] ?: return message.content
        var result = template.replace("{actor}", message.senderName?.takeIf { it.isNotBlank() } ?: someone)
        Regex("\\{([a-z_]+)\\}").findAll(template).forEach { match ->
            val key = match.groupValues[1]
            if (key != "actor") result = result.replace("{$key}", message.activityValue(key) ?: "")
        }
        return result
    }

    companion object {
        val current: ChatStrings get() = AppLocale.pick(en, es)

        val en = ChatStrings(
            ai = "AI", details = "Conversation details", close = "Close", retry = "Try again", cancel = "Cancel", save = "Save", done = "Done",
            open = "Open", resolved = "Resolved", resolve = "Resolve", resolveTitle = "Resolve this conversation?",
            resolveHint = "This case will become read-only. The contact's next message starts a new case.",
            resolvedHint = "This case is resolved. The contact's next message starts a new conversation.",
            resolveConfirm = "Resolve", assignee = "Assigned to", unassigned = "Unassigned", team = "Team", noTeam = "No team", me = "You",
            agent = "Assistant", visitor = "Contact", windowClosed = "WhatsApp reply window closed",
            windowHint = "Send an approved template to reach this contact. Free-form replies are available for 24 hours after they write.",
            socialBlocked = "Replies unavailable", socialWindowHint = "Wait for a new message from this contact. Templates cannot reopen this channel's reply window.",
            socialHumanOnly = "Human replies only", socialHumanHint = "The approved human support window is active. Automated replies are unavailable after 24 hours.",
            unsupportedAttachment = "This channel does not support this attachment. Instagram documents must be PDF files.", actions = "Message actions",
            quote = "Reply to message", quoting = "Replying to", cancelQuote = "Cancel quoted reply", unavailableQuote = "Earlier message", react = "React", removeReaction = "Remove reaction",
            sent = "Sent", delivered = "Delivered", read = "Read", pending = "Sending", unknown = "Delivery unconfirmed", failed = "Delivery failed", someone = "Someone",
            newMessages = "New messages", latest = "Go to latest message", updateFailed = "Could not update this conversation",
            canned = "Saved replies", noCanned = "No saved replies yet. Create them in Settings.", searchReplies = "Search saved replies",
            file = "Choose a file", removeFile = "Remove attachment", attachmentFailed = "Could not open this attachment", attachmentRetry = "Download again",
            audioFailed = "Could not load audio", openFile = "Open attachment", viewImage = "View full image",
            caption = "Add a caption", attached = "Ready to send", pickFailed = "Could not select that file", recordFailed = "Could not finish recording. Try again.",
            recordAudio = "Record audio", audioReady = "Audio message",
            micUnavailable = "The microphone is unavailable. Check microphone access in Settings.", recordingTooShort = "Recording is too short. Try again.",
            events = mapOf(
                "resolved" to "{actor} resolved the conversation", "reopened" to "{actor} reopened the conversation", "reopened_by_contact" to "The contact wrote again",
                "taken_over" to "{actor} took over the conversation", "returned_to_ai" to "{actor} returned the conversation to the assistant",
                "auto_resolved" to "Resolved automatically after {hours} h without activity", "self_assigned" to "{actor} is now handling the conversation",
                "resolved_by_agent" to "{actor} resolved the conversation: {reason}", "closed_unanswered" to "Resolved after {hours} h without an answer to the follow-ups",
                "assigned" to "{actor} assigned the conversation to {assignee}", "unassigned" to "{actor} removed the assignment", "team_changed" to "{actor} moved the conversation to {team}",
            ),
        )

        val es = ChatStrings(
            ai = "IA", details = "Detalles de la conversación", close = "Cerrar", retry = "Reintentar", cancel = "Cancelar", save = "Guardar", done = "Listo",
            open = "Abierta", resolved = "Resuelta", resolve = "Resolver", resolveTitle = "¿Resolver esta conversación?",
            resolveHint = "Este caso quedará cerrado. El siguiente mensaje del contacto iniciará un caso nuevo.",
            resolvedHint = "Este caso está resuelto. El siguiente mensaje del contacto iniciará una conversación nueva.",
            resolveConfirm = "Resolver", assignee = "Responsable", unassigned = "Sin asignar", team = "Equipo", noTeam = "Sin equipo", me = "Tú",
            agent = "Asistente", visitor = "Contacto", windowClosed = "La ventana de WhatsApp está cerrada",
            windowHint = "Envía una plantilla aprobada para contactar a esta persona. Puedes responder libremente durante 24 horas después de que te escriba.",
            socialBlocked = "No se puede responder", socialWindowHint = "Espera un mensaje nuevo de este contacto. Las plantillas no pueden reabrir la ventana de respuesta de este canal.",
            socialHumanOnly = "Solo respuestas humanas", socialHumanHint = "La ventana aprobada de atención humana está activa. Las respuestas automáticas no están disponibles después de 24 horas.",
            unsupportedAttachment = "Este canal no admite este adjunto. Los documentos de Instagram deben ser PDF.", actions = "Acciones del mensaje",
            quote = "Responder al mensaje", quoting = "Respondiendo a", cancelQuote = "Cancelar respuesta citada", unavailableQuote = "Mensaje anterior", react = "Reaccionar", removeReaction = "Quitar reacción",
            sent = "Enviado", delivered = "Entregado", read = "Leído", pending = "Enviando", unknown = "Entrega sin confirmar", failed = "Error de entrega", someone = "Alguien",
            newMessages = "Mensajes nuevos", latest = "Ir al último mensaje", updateFailed = "No se pudo actualizar esta conversación",
            canned = "Respuestas guardadas", noCanned = "Todavía no hay respuestas guardadas. Créalas en Configuración.", searchReplies = "Buscar respuestas guardadas",
            file = "Elegir un archivo", removeFile = "Quitar adjunto", attachmentFailed = "No se pudo abrir este adjunto", attachmentRetry = "Descargar de nuevo",
            audioFailed = "No se pudo cargar el audio", openFile = "Abrir adjunto", viewImage = "Ver imagen completa",
            caption = "Añade un mensaje", attached = "Listo para enviar", pickFailed = "No se pudo seleccionar ese archivo", recordFailed = "No se pudo terminar la grabación. Inténtalo de nuevo.",
            recordAudio = "Grabar audio", audioReady = "Mensaje de audio",
            micUnavailable = "El micrófono no está disponible. Revisa el acceso al micrófono en Ajustes.", recordingTooShort = "La grabación es demasiado corta. Inténtalo de nuevo.",
            events = mapOf(
                "resolved" to "{actor} resolvió la conversación", "reopened" to "{actor} reabrió la conversación", "reopened_by_contact" to "El contacto volvió a escribir",
                "taken_over" to "{actor} tomó la conversación", "returned_to_ai" to "{actor} devolvió la conversación al asistente",
                "auto_resolved" to "Resuelta automáticamente tras {hours} h sin actividad", "self_assigned" to "{actor} está atendiendo la conversación",
                "resolved_by_agent" to "{actor} resolvió la conversación: {reason}", "closed_unanswered" to "Resuelta después de {hours} h sin respuesta a los mensajes de seguimiento",
                "assigned" to "{actor} asignó la conversación a {assignee}", "unassigned" to "{actor} quitó la asignación", "team_changed" to "{actor} pasó la conversación a {team}",
            ),
        )
    }
}
