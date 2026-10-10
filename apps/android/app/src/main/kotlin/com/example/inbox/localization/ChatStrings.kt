package com.example.inbox.localization

/** Typed conversation copy, selected using the device language. */
class ChatStrings(
    val ai: String, val details: String, val close: String, val retry: String, val cancel: String, val save: String, val done: String,
    val open: String, val resolved: String, val resolve: String, val resolveTitle: String, val resolveHint: String, val resolvedHint: String,
    val resolveConfirm: String, val assignee: String, val unassigned: String, val team: String, val noTeam: String, val me: String,
    val windowClosed: String, val windowHint: String, val newMessages: String, val latest: String, val updateFailed: String,
) {
    companion object {
        val current: ChatStrings get() = AppLocale.pick(en, es)
        val en = ChatStrings(
            ai = "Assistant", details = "Details", close = "Close", retry = "Try again", cancel = "Cancel", save = "Save", done = "Done",
            open = "Open", resolved = "Resolved", resolve = "Resolve", resolveTitle = "Resolve this conversation?",
            resolveHint = "A resolved case is final. A new message from the customer opens a new case.",
            resolvedHint = "This case is resolved. New messages from the customer open a new case.",
            resolveConfirm = "Resolve", assignee = "Assignee", unassigned = "Unassigned", team = "Team", noTeam = "No team", me = "Me",
            windowClosed = "The reply window is closed", windowHint = "The channel only allows replies within its window after the customer's last message.",
            newMessages = "New messages", latest = "Jump to the latest message", updateFailed = "Could not update",
        )
        val es = ChatStrings(
            ai = "Asistente", details = "Detalles", close = "Cerrar", retry = "Reintentar", cancel = "Cancelar", save = "Guardar", done = "Listo",
            open = "Abierta", resolved = "Resuelta", resolve = "Resolver", resolveTitle = "¿Resolver esta conversación?",
            resolveHint = "Un caso resuelto es definitivo. Un mensaje nuevo del cliente abre otro caso.",
            resolvedHint = "Este caso está resuelto. Los mensajes nuevos del cliente abren otro caso.",
            resolveConfirm = "Resolver", assignee = "Responsable", unassigned = "Sin asignar", team = "Equipo", noTeam = "Sin equipo", me = "Yo",
            windowClosed = "La ventana de respuesta está cerrada", windowHint = "El canal solo permite responder dentro de su ventana tras el último mensaje del cliente.",
            newMessages = "Mensajes nuevos", latest = "Ir al último mensaje", updateFailed = "No pudimos actualizar",
        )
    }
}
