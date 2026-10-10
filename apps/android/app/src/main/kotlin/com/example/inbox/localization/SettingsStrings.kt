package com.example.inbox.localization

/** Settings copy: the workspace catalogues and the account. */
class SettingsStrings(
    val title: String, val subtitle: String, val workspace: String, val account: String, val teams: String, val tags: String, val canned: String,
    val templates: String, val readOnly: String, val tagsHint: String, val newTag: String, val editTag: String, val tagName: String, val tagColor: String,
    val deleteTag: String, val deleteTagBody: String, val noTags: String, val contacts: String, val routesTo: String, val cannedHint: String,
    val newReply: String, val editReply: String, val shortcut: String, val shortcutHint: String, val content: String, val variablesHint: String,
    val deleteReply: String, val deleteReplyBody: String, val noCanned: String, val templatesHint: String, val noTemplates: String, val noLine: String,
    val pendingReview: String, val deleteTemplate: String, val deleteTemplateBody: String, val templatesWebOnly: String,
    val save: String, val cancel: String, val delete: String, val retry: String, val loadFailed: String, val saveFailed: String, val duplicate: String,
    val availability: String, val signOut: String,
) {
    fun status(value: String): String = when (value.uppercase()) {
        "APPROVED" -> AppLocale.pick("Approved", "Aprobada")
        "REJECTED" -> AppLocale.pick("Rejected", "Rechazada")
        "PENDING", "IN_REVIEW" -> pendingReview
        "PAUSED" -> AppLocale.pick("Paused", "Pausada")
        else -> value.lowercase().replaceFirstChar { it.uppercase() }
    }

    companion object {
        val current: SettingsStrings get() = AppLocale.pick(en, es)

        val en = SettingsStrings(
            title = "Settings", subtitle = "Your workspace and your account", workspace = "Workspace", account = "Account",
            teams = "Teams", tags = "Tags", canned = "Saved replies", templates = "WhatsApp templates", readOnly = "Your administrator manages this list.",
            tagsHint = "Label contacts to find them and route their conversations.", newTag = "New tag", editTag = "Edit tag", tagName = "Name", tagColor = "Color",
            deleteTag = "Delete tag?", deleteTagBody = "The tag is removed from every contact that has it.", noTags = "No tags yet", contacts = "contacts", routesTo = "Routes to",
            cannedHint = "Type / in a conversation to insert one.", newReply = "New reply", editReply = "Edit reply", shortcut = "Shortcut",
            shortcutHint = "Lowercase letters, numbers, - and _ only.", content = "Reply",
            variablesHint = "Variables: {contact_name}, {contact_phone}, {contact_email}, {agent_name}.",
            deleteReply = "Delete saved reply?", deleteReplyBody = "It stops being offered in conversations.", noCanned = "No saved replies yet",
            templatesHint = "Approved templates reach contacts outside the 24 hour window. Meta reviews each one.", noTemplates = "No templates yet",
            noLine = "Connect a WhatsApp Business line on the web to use templates.", pendingReview = "In review",
            deleteTemplate = "Delete template?", deleteTemplateBody = "It is removed from Meta and can no longer be sent.", templatesWebOnly = "New templates are created on the web for now.",
            save = "Save", cancel = "Cancel", delete = "Delete", retry = "Try again", loadFailed = "Could not load", saveFailed = "Could not save",
            duplicate = "That name is already in use.", availability = "Availability", signOut = "Sign out",
        )

        val es = SettingsStrings(
            title = "Configuración", subtitle = "Tu espacio y tu cuenta", workspace = "Espacio de trabajo", account = "Cuenta",
            teams = "Equipos", tags = "Etiquetas", canned = "Respuestas guardadas", templates = "Plantillas de WhatsApp", readOnly = "Tu administrador gestiona esta lista.",
            tagsHint = "Etiqueta contactos para encontrarlos y dirigir sus conversaciones.", newTag = "Nueva etiqueta", editTag = "Editar etiqueta", tagName = "Nombre", tagColor = "Color",
            deleteTag = "¿Eliminar la etiqueta?", deleteTagBody = "Se quita de todos los contactos que la tienen.", noTags = "Todavía no hay etiquetas", contacts = "contactos", routesTo = "Dirige a",
            cannedHint = "Escribe / en una conversación para insertar una.", newReply = "Nueva respuesta", editReply = "Editar respuesta", shortcut = "Atajo",
            shortcutHint = "Solo minúsculas, números, - y _.", content = "Respuesta",
            variablesHint = "Variables: {contact_name}, {contact_phone}, {contact_email}, {agent_name}.",
            deleteReply = "¿Eliminar la respuesta guardada?", deleteReplyBody = "Deja de ofrecerse en las conversaciones.", noCanned = "Todavía no hay respuestas guardadas",
            templatesHint = "Las plantillas aprobadas llegan a contactos fuera de la ventana de 24 horas. Meta revisa cada una.", noTemplates = "Todavía no hay plantillas",
            noLine = "Conecta una línea de WhatsApp Business desde la web para usar plantillas.", pendingReview = "En revisión",
            deleteTemplate = "¿Eliminar la plantilla?", deleteTemplateBody = "Se elimina de Meta y ya no se puede enviar.", templatesWebOnly = "Las plantillas nuevas se crean desde la web por ahora.",
            save = "Guardar", cancel = "Cancelar", delete = "Eliminar", retry = "Reintentar", loadFailed = "No se pudo cargar", saveFailed = "No se pudo guardar",
            duplicate = "Ese nombre ya está en uso.", availability = "Disponibilidad", signOut = "Salir",
        )
    }
}
