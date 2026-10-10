package com.example.inbox.localization

/** Typed directory copy in the same languages as the inbox. */
class ContactsStrings(
    val title: String, val subtitle: String, val search: String, val newContact: String, val empty: String, val emptyHint: String, val noMatches: String,
    val back: String, val close: String, val cancel: String, val save: String, val edit: String, val name: String, val phone: String, val email: String,
    val phoneHint: String, val invalidPhone: String, val invalidEmail: String, val notes: String, val notesHint: String, val noNotes: String, val unnamed: String,
    val history: String, val noHistory: String, val open: String, val resolved: String, val human: String, val ai: String,
    val start: String, val send: String, val chooseLine: String, val noLine: String, val message: String, val startHint: String, val templateHint: String,
    val retry: String, val loadFailed: String, val saveFailed: String, val sendFailed: String, val noPhone: String, val existing: String,
    val conversation: String, val conversations: String, val openCase: String, val openCases: String, val noMessages: String, val duplicatePhone: String,
    val tags: String, val editTags: String, val noTags: String, val noTagsDefined: String, val done: String, val templatesWebOnly: String,
) {
    companion object {
        val current: ContactsStrings get() = AppLocale.pick(en, es)

        val en = ContactsStrings(
            title = "Contacts", subtitle = "People behind your conversations", search = "Search name, phone or email", newContact = "New contact",
            empty = "No contacts yet", emptyHint = "Add a contact or wait for someone to write to your inbox.", noMatches = "No matching contacts",
            back = "Back", close = "Close", cancel = "Cancel", save = "Save contact", edit = "Edit contact", name = "Name", phone = "Phone", email = "Email",
            phoneHint = "Include the country code, for example +57 300 123 4567.", invalidPhone = "Enter a valid phone number with its country code.", invalidEmail = "Enter a valid email address.",
            notes = "Contact notes", notesHint = "Visible to your team. These notes stay with the contact.", noNotes = "No notes yet", unnamed = "Contact",
            history = "Conversation history", noHistory = "No conversations yet", open = "Open", resolved = "Resolved", human = "Team", ai = "Assistant",
            start = "Start conversation", send = "Send message", chooseLine = "Choose a WhatsApp line", noLine = "No WhatsApp line is available to start a conversation.",
            message = "Message", startHint = "This sends a message to the contact and assigns the new conversation to you.",
            templateHint = "This line needs an approved template for the first message.",
            retry = "Try again", loadFailed = "Could not load contacts", saveFailed = "Could not save this contact", sendFailed = "Could not start the conversation",
            noPhone = "Add a phone number to start a conversation.", existing = "There is already an open conversation on this line.",
            conversation = "conversation", conversations = "conversations", openCase = "open", openCases = "open", noMessages = "No messages yet", duplicatePhone = "A contact with this phone number already exists.",
            tags = "Tags", editTags = "Edit tags", noTags = "No tags", noTagsDefined = "No tags yet. Create them in Settings.", done = "Done",
            templatesWebOnly = "Sending templates from here is not available yet; use the web for this line.",
        )

        val es = ContactsStrings(
            title = "Contactos", subtitle = "Las personas de tu bandeja", search = "Buscar nombre, teléfono o correo", newContact = "Nuevo contacto",
            empty = "Todavía no hay contactos", emptyHint = "Agrega un contacto o espera a que alguien escriba a tu bandeja.", noMatches = "No hay contactos que coincidan",
            back = "Atrás", close = "Cerrar", cancel = "Cancelar", save = "Guardar contacto", edit = "Editar contacto", name = "Nombre", phone = "Teléfono", email = "Correo",
            phoneHint = "Incluye el código de país, por ejemplo +57 300 123 4567.", invalidPhone = "Escribe un teléfono válido con el código de país.", invalidEmail = "Escribe un correo válido.",
            notes = "Notas del contacto", notesHint = "Visibles para tu equipo. Estas notas se guardan con el contacto.", noNotes = "Todavía no hay notas", unnamed = "Contacto",
            history = "Historial de conversaciones", noHistory = "Todavía no hay conversaciones", open = "Abierta", resolved = "Resuelta", human = "Equipo", ai = "Asistente",
            start = "Iniciar conversación", send = "Enviar mensaje", chooseLine = "Elige una línea de WhatsApp", noLine = "No hay una línea de WhatsApp disponible para iniciar una conversación.",
            message = "Mensaje", startHint = "Esto envía un mensaje al contacto y te asigna la nueva conversación.",
            templateHint = "Esta línea necesita una plantilla aprobada para el primer mensaje.",
            retry = "Reintentar", loadFailed = "No pudimos cargar los contactos", saveFailed = "No pudimos guardar el contacto", sendFailed = "No pudimos iniciar la conversación",
            noPhone = "Agrega un teléfono para iniciar una conversación.", existing = "Ya existe una conversación abierta en esta línea.",
            conversation = "conversación", conversations = "conversaciones", openCase = "abierta", openCases = "abiertas", noMessages = "Sin mensajes todavía", duplicatePhone = "Ya existe un contacto con este teléfono.",
            tags = "Etiquetas", editTags = "Editar etiquetas", noTags = "Sin etiquetas", noTagsDefined = "Todavía no hay etiquetas. Créalas en Configuración.", done = "Listo",
            templatesWebOnly = "Enviar plantillas desde aquí todavía no está disponible; usa la web para esta línea.",
        )
    }
}
