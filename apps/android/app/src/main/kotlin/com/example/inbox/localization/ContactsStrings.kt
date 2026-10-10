package com.example.inbox.localization

/** Typed directory copy in the same languages as the inbox. */
class ContactsStrings(
    val title: String, val subtitle: String, val search: String, val empty: String, val noMatches: String, val unnamed: String,
    val history: String, val noHistory: String, val retry: String, val loadFailed: String,
    val conversation: String, val conversations: String, val openCase: String, val openCases: String,
) {
    companion object {
        val current: ContactsStrings get() = AppLocale.pick(en, es)
        val en = ContactsStrings(
            title = "Contacts", subtitle = "Everyone who has written to your workspace", search = "Search name, phone or e-mail",
            empty = "No contacts yet", noMatches = "No matching contacts", unnamed = "Unnamed contact",
            history = "Conversations", noHistory = "No conversations yet", retry = "Try again", loadFailed = "Could not load contacts",
            conversation = "conversation", conversations = "conversations", openCase = "open", openCases = "open",
        )
        val es = ContactsStrings(
            title = "Contactos", subtitle = "Todas las personas que han escrito a tu espacio", search = "Busca un nombre, teléfono o correo",
            empty = "Todavía no hay contactos", noMatches = "No hay contactos que coincidan", unnamed = "Contacto sin nombre",
            history = "Conversaciones", noHistory = "Todavía no hay conversaciones", retry = "Reintentar", loadFailed = "No pudimos cargar los contactos",
            conversation = "conversación", conversations = "conversaciones", openCase = "abierta", openCases = "abiertas",
        )
    }
}
