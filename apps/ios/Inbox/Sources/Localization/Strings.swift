import Foundation

/// Interface copy shared by the sign-in, inbox, chat and composer screens.
///
/// Both languages are instances of one struct, so a label that exists in one and
/// not the other is a compile error rather than a blank someone finds in
/// production. Screens read `Strings.current.inbox.title`; nothing can miss at
/// runtime.
struct Strings {
    struct SignIn {
        let title, subtitle, serverLabel, serverPlaceholder, serverHint, portalLabel, portalHint, otherServer: String
        let workspaceLabel, workspacePlaceholder, workspaceHint, workspaceUnavailable, incorrectCredentials: String
        let emailLabel, emailPlaceholder, passwordLabel, submit, failed, invalidWorkspace, invalidServer: String
        let connectedTo, changeServer, useHosted, forgot, forgotTitle, forgotBody, chooseAccount, chooseAccountBody, serverSheetTitle: String
        let serverTitle, connect: String
    }
    struct Inbox {
        let title, all, unread, mine, ai, open, resolved, search, filters, teams, allTeams, allChannels: String
        let done, retry, loadingMore, loadMore, noResults, noResultsBody, clearFilters, account, online, away: String
        let availabilityHint, aiHandling, assignedTo, legacyHuman, signOutTitle, cancel, signOut: String
        let reconnectTitle, reconnectBody, sessionExpired, notificationUnavailable, contacts, connectionError, loading: String
    }
    struct List {
        let signOut, emptyTitle, emptyBody, loadFailed, noMessages, youReply, untitled, webVisitor: String
    }
    struct Chat {
        let back, youAreReplying, assistantIsReplying, takeOver, handBack, takeOverWide, empty: String
        let loadFailed, modeFailed, sendFailed, fileFailed: String
    }
    struct Composer {
        let placeholder, attach, send, fromLibrary, fromCamera, sheetTitle, cancel, record, recording: String
        let discard, discardLabel, pause, resume, sendVoice, cameraDeniedTitle, photosDeniedTitle, mediaDeniedBody: String
        let micDeniedTitle, micDeniedBody, recordFailedTitle, recordFailedBody: String
    }
    struct Attachment {
        let imageUnavailable, generic, image, play, pause: String
    }
    struct Channels {
        let whatsapp, instagram, messenger, widget, playground: String
    }
    struct When {
        let today, yesterday: String
    }
    struct Errors {
        let unreachable, generic, sendFile: String
    }

    let signIn: SignIn
    let inbox: Inbox
    let list: List
    let chat: Chat
    let composer: Composer
    let attachment: Attachment
    let channels: Channels
    let when: When
    let errors: Errors

    static var current: Strings { AppLocale.pick(en, es) }

    static let en = Strings(
        signIn: SignIn(
            title: "Log in to your account",
            subtitle: "Use the e-mail and password your agency gave you.",
            serverLabel: "Server address",
            serverPlaceholder: "chat.myagency.com",
            serverHint: "The address of the instance your agency runs.",
            portalLabel: "Your portal address",
            portalHint: "The same address you open in your browser.",
            otherServer: "Another server",
            workspaceLabel: "Workspace",
            workspacePlaceholder: "your-agency",
            workspaceHint: "Enter your workspace name or paste its address.",
            workspaceUnavailable: "This workspace is unavailable. Check its address or contact your administrator.",
            incorrectCredentials: "Incorrect email or password. Use your inbox operator account.",
            emailLabel: "E-mail",
            emailPlaceholder: "you@business.com",
            passwordLabel: "Password",
            submit: "Sign in",
            failed: "Could not sign in",
            invalidWorkspace: "Enter your workspace name or its HTTPS address.",
            invalidServer: "Enter a valid server address.",
            connectedTo: "You are connected to {name}.", changeServer: "Change server", useHosted: "Use {name}",
            forgot: "Forgot your password?", forgotTitle: "Your agency manages your access",
            forgotBody: "Ask the people who gave you this account to set a new password for you.",
            chooseAccount: "Which account?", chooseAccountBody: "This e-mail opens more than one inbox. Pick the one you want to work in.",
            serverSheetTitle: "Server", serverTitle: "Connect to your server", connect: "Continue"
        ),
        inbox: Inbox(
            title: "Inbox", all: "All", unread: "Unread", mine: "Mine", ai: "AI", open: "Open", resolved: "Resolved",
            search: "Search name, phone or message", filters: "Filters", teams: "Teams", allTeams: "All teams", allChannels: "All channels",
            done: "Done", retry: "Try again", loadingMore: "Loading more…", loadMore: "Load more",
            noResults: "No matching conversations", noResultsBody: "Try another search or filter.", clearFilters: "Clear filters",
            account: "Your account", online: "Available", away: "Away",
            availabilityHint: "Available team members can receive new assignments.",
            aiHandling: "AI is replying", assignedTo: "Assigned to", legacyHuman: "Human support",
            signOutTitle: "Sign out of this inbox?", cancel: "Cancel", signOut: "Sign out",
            reconnectTitle: "Could not connect",
            reconnectBody: "Your session is saved. Check your connection and try again.",
            sessionExpired: "Your session expired. Sign in again.",
            notificationUnavailable: "This conversation is no longer available.",
            contacts: "Contacts",
            connectionError: "Could not refresh. Showing the last loaded conversations.", loading: "Loading"
        ),
        list: List(
            signOut: "Sign out", emptyTitle: "No conversations yet",
            emptyBody: "When someone writes to your assistant, the conversation shows up here.",
            loadFailed: "Could not load conversations", noMessages: "No messages yet", youReply: "You reply",
            untitled: "Conversation", webVisitor: "Web visitor"
        ),
        chat: Chat(
            back: "Back", youAreReplying: "You are replying", assistantIsReplying: "The assistant is replying",
            takeOver: "Take over", handBack: "Hand back", takeOverWide: "Take over to reply yourself",
            empty: "No messages in this conversation yet.", loadFailed: "Could not load this conversation",
            modeFailed: "Could not change the mode", sendFailed: "Could not send", fileFailed: "Could not send that file"
        ),
        composer: Composer(
            placeholder: "Message", attach: "Add an attachment", send: "Send", fromLibrary: "Photo & Video Library",
            fromCamera: "Camera", sheetTitle: "Attach", cancel: "Cancel", record: "Record a voice note", recording: "Starting…",
            discard: "Cancel", discardLabel: "Delete recording", pause: "Pause recording", resume: "Resume recording",
            sendVoice: "Send voice note", cameraDeniedTitle: "Camera access is off", photosDeniedTitle: "Photo access is off",
            mediaDeniedBody: "Turn it on in Settings to send photos from here.",
            micDeniedTitle: "Microphone access is off", micDeniedBody: "Turn it on in Settings to send voice notes.",
            recordFailedTitle: "Could not start recording", recordFailedBody: "Try again in a moment."
        ),
        attachment: Attachment(
            imageUnavailable: "Image unavailable", generic: "Attachment", image: "Attached image",
            play: "Play voice note", pause: "Pause voice note"
        ),
        channels: Channels(whatsapp: "WhatsApp", instagram: "Instagram", messenger: "Facebook Messenger", widget: "Web chat", playground: "Playground"),
        when: When(today: "Today", yesterday: "Yesterday"),
        errors: Errors(
            unreachable: "Could not reach that server. Check the address and that you are on the same network.",
            generic: "Something went wrong", sendFile: "Could not send that file"
        )
    )

    static let es = Strings(
        signIn: SignIn(
            title: "Entra a tu cuenta",
            subtitle: "Usa el correo y la contraseña que te dio tu agencia.",
            serverLabel: "Dirección del servidor",
            serverPlaceholder: "chat.miagencia.com",
            serverHint: "La dirección de la instancia que tu agencia tiene montada.",
            portalLabel: "Dirección de tu portal",
            portalHint: "La misma dirección que abres en el navegador.",
            otherServer: "Otro servidor",
            workspaceLabel: "Espacio de trabajo",
            workspacePlaceholder: "tu-agencia",
            workspaceHint: "Escribe el nombre de tu espacio o pega su dirección.",
            workspaceUnavailable: "Este espacio no está disponible. Revisa la dirección o contacta a tu administrador.",
            incorrectCredentials: "Correo o contraseña incorrectos. Usa tu cuenta de operador de la bandeja.",
            emailLabel: "Correo",
            emailPlaceholder: "tu@negocio.com",
            passwordLabel: "Contraseña",
            submit: "Entrar",
            failed: "No pudimos iniciar sesión",
            invalidWorkspace: "Escribe el nombre de tu espacio o su dirección HTTPS.",
            invalidServer: "Escribe una dirección de servidor válida.",
            connectedTo: "Estás conectado a {name}.", changeServer: "Cambiar servidor", useHosted: "Usar {name}",
            forgot: "¿Olvidaste tu contraseña?", forgotTitle: "Tu agencia gestiona tu acceso",
            forgotBody: "Pídele a quien te dio esta cuenta que te asigne una contraseña nueva.",
            chooseAccount: "¿Cuál cuenta?", chooseAccountBody: "Este correo abre más de una bandeja. Elige en cuál quieres trabajar.",
            serverSheetTitle: "Servidor", serverTitle: "Conéctate a tu servidor", connect: "Continuar"
        ),
        inbox: Inbox(
            title: "Bandeja de entrada", all: "Todos", unread: "No leídos", mine: "Míos", ai: "IA", open: "Abiertos", resolved: "Resueltos",
            search: "Busca un nombre, teléfono o mensaje", filters: "Filtros", teams: "Equipos", allTeams: "Todos los equipos", allChannels: "Todos los canales",
            done: "Listo", retry: "Reintentar", loadingMore: "Cargando más…", loadMore: "Cargar más",
            noResults: "No hay conversaciones que coincidan", noResultsBody: "Prueba otra búsqueda o filtro.", clearFilters: "Quitar filtros",
            account: "Tu cuenta", online: "Disponible", away: "Ausente",
            availabilityHint: "Los miembros disponibles pueden recibir nuevas asignaciones.",
            aiHandling: "Responde la IA", assignedTo: "Asignado a", legacyHuman: "Atención humana",
            signOutTitle: "¿Salir de esta bandeja?", cancel: "Cancelar", signOut: "Salir",
            reconnectTitle: "No pudimos conectar",
            reconnectBody: "Tu sesión está guardada. Revisa la conexión e inténtalo de nuevo.",
            sessionExpired: "Tu sesión venció. Vuelve a entrar.",
            notificationUnavailable: "Esta conversación ya no está disponible.",
            contacts: "Contactos",
            connectionError: "No pudimos actualizar. Mostramos las últimas conversaciones cargadas.", loading: "Cargando"
        ),
        list: List(
            signOut: "Salir", emptyTitle: "Todavía no hay conversaciones",
            emptyBody: "Cuando alguien le escriba a tu asistente, la conversación aparece aquí.",
            loadFailed: "No pudimos cargar las conversaciones", noMessages: "Sin mensajes todavía", youReply: "Respondes tú",
            untitled: "Conversación", webVisitor: "Visitante web"
        ),
        chat: Chat(
            back: "Atrás", youAreReplying: "Estás respondiendo tú", assistantIsReplying: "Está respondiendo el asistente",
            takeOver: "Tomar", handBack: "Devolver", takeOverWide: "Toma la conversación para responder tú",
            empty: "Esta conversación todavía no tiene mensajes.", loadFailed: "No pudimos cargar esta conversación",
            modeFailed: "No pudimos cambiar el modo", sendFailed: "No se pudo enviar", fileFailed: "No se pudo enviar ese archivo"
        ),
        composer: Composer(
            placeholder: "Mensaje", attach: "Adjuntar", send: "Enviar", fromLibrary: "Fotos y videos",
            fromCamera: "Cámara", sheetTitle: "Adjuntar", cancel: "Cancelar", record: "Grabar una nota de voz", recording: "Empezando…",
            discard: "Cancelar", discardLabel: "Borrar la grabación", pause: "Pausar la grabación", resume: "Seguir grabando",
            sendVoice: "Enviar la nota de voz", cameraDeniedTitle: "La cámara está bloqueada", photosDeniedTitle: "Las fotos están bloqueadas",
            mediaDeniedBody: "Actívalo en Ajustes para poder enviar fotos desde aquí.",
            micDeniedTitle: "El micrófono está bloqueado", micDeniedBody: "Actívalo en Ajustes para poder enviar notas de voz.",
            recordFailedTitle: "No pudimos empezar a grabar", recordFailedBody: "Inténtalo de nuevo en un momento."
        ),
        attachment: Attachment(
            imageUnavailable: "La imagen no está disponible", generic: "Adjunto", image: "Imagen adjunta",
            play: "Reproducir la nota de voz", pause: "Pausar la nota de voz"
        ),
        channels: Channels(whatsapp: "WhatsApp", instagram: "Instagram", messenger: "Facebook Messenger", widget: "Chat web", playground: "Pruebas"),
        when: When(today: "Hoy", yesterday: "Ayer"),
        errors: Errors(
            unreachable: "No pudimos llegar a ese servidor. Revisa la dirección y que estés en la misma red.",
            generic: "Algo salió mal", sendFile: "No se pudo enviar ese archivo"
        )
    )
}
