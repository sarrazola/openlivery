package com.example.inbox.localization

/**
 * Interface copy shared by the sign-in, inbox, chat and composer screens.
 *
 * Both languages are instances of one class, so a label that exists in one and
 * not the other is a compile error rather than a blank someone finds in
 * production. Screens read `Strings.current.inbox.title`; nothing can miss at
 * runtime.
 */
class Strings(
    val signIn: SignIn, val inbox: Inbox, val list: ListCopy, val chat: Chat, val composer: Composer,
    val attachment: AttachmentCopy, val channels: Channels, val `when`: When, val errors: Errors,
) {
    class SignIn(
        val title: String, val subtitle: String, val serverLabel: String, val serverPlaceholder: String, val serverHint: String,
        val otherServer: String, val workspaceLabel: String, val workspacePlaceholder: String, val workspaceHint: String,
        val workspaceUnavailable: String, val incorrectCredentials: String, val emailLabel: String, val emailPlaceholder: String,
        val passwordLabel: String, val submit: String, val failed: String, val invalidWorkspace: String, val invalidServer: String,
        val connectedTo: String, val changeServer: String, val useHosted: String, val forgot: String, val forgotTitle: String,
        val forgotBody: String, val chooseAccount: String, val chooseAccountBody: String, val serverTitle: String, val connect: String,
    )
    class Inbox(
        val title: String, val all: String, val unread: String, val mine: String, val ai: String, val open: String, val resolved: String,
        val search: String, val filters: String, val teams: String, val allTeams: String, val allChannels: String, val done: String,
        val retry: String, val loadingMore: String, val loadMore: String, val noResults: String, val noResultsBody: String,
        val clearFilters: String, val account: String, val online: String, val away: String, val availabilityHint: String,
        val aiHandling: String, val assignedTo: String, val legacyHuman: String, val signOutTitle: String, val cancel: String,
        val signOut: String, val reconnectTitle: String, val reconnectBody: String, val sessionExpired: String,
        val notificationUnavailable: String, val contacts: String, val connectionError: String, val loading: String, val tabTitle: String,
    )
    class ListCopy(
        val signOut: String, val emptyTitle: String, val emptyBody: String, val loadFailed: String, val noMessages: String,
        val youReply: String, val untitled: String, val webVisitor: String,
    )
    class Chat(
        val back: String, val youAreReplying: String, val assistantIsReplying: String, val takeOver: String, val handBack: String,
        val takeOverWide: String, val empty: String, val loadFailed: String, val modeFailed: String, val sendFailed: String, val fileFailed: String,
    )
    class Composer(
        val placeholder: String, val attach: String, val send: String, val fromLibrary: String, val fromCamera: String, val sheetTitle: String,
        val cancel: String, val record: String, val recording: String, val discard: String, val discardLabel: String, val pause: String,
        val resume: String, val sendVoice: String, val cameraDeniedTitle: String, val photosDeniedTitle: String, val mediaDeniedBody: String,
        val micDeniedTitle: String, val micDeniedBody: String, val recordFailedTitle: String, val recordFailedBody: String,
    )
    class AttachmentCopy(val imageUnavailable: String, val generic: String, val image: String, val play: String, val pause: String)
    class Channels(val whatsapp: String, val instagram: String, val messenger: String, val widget: String, val playground: String)
    class When(val today: String, val yesterday: String)
    class Errors(val unreachable: String, val generic: String, val sendFile: String)

    companion object {
        val current: Strings get() = AppLocale.pick(en, es)

        val en = Strings(
            signIn = SignIn(
                title = "Log in to your account", subtitle = "Use the e-mail and password your agency gave you.",
                serverLabel = "Server address", serverPlaceholder = "chat.myagency.com", serverHint = "The address of the instance your agency runs.",
                otherServer = "Another server", workspaceLabel = "Workspace", workspacePlaceholder = "your-agency",
                workspaceHint = "Enter your workspace name or paste its address.",
                workspaceUnavailable = "This workspace is unavailable. Check its address or contact your administrator.",
                incorrectCredentials = "Incorrect email or password. Use your inbox operator account.",
                emailLabel = "E-mail", emailPlaceholder = "you@business.com", passwordLabel = "Password", submit = "Sign in",
                failed = "Could not sign in", invalidWorkspace = "Enter your workspace name or its HTTPS address.",
                invalidServer = "Enter a valid server address.", connectedTo = "You are connected to {name}.", changeServer = "Change server",
                useHosted = "Use {name}", forgot = "Forgot your password?", forgotTitle = "Your agency manages your access",
                forgotBody = "Ask the people who gave you this account to set a new password for you.",
                chooseAccount = "Which account?", chooseAccountBody = "This e-mail opens more than one inbox. Pick the one you want to work in.",
                serverTitle = "Connect to your server", connect = "Continue",
            ),
            inbox = Inbox(
                title = "Inbox", all = "All", unread = "Unread", mine = "Mine", ai = "AI", open = "Open", resolved = "Resolved",
                search = "Search name, phone or message", filters = "Filters", teams = "Teams", allTeams = "All teams", allChannels = "All channels",
                done = "Done", retry = "Try again", loadingMore = "Loading more…", loadMore = "Load more",
                noResults = "No matching conversations", noResultsBody = "Try another search or filter.", clearFilters = "Clear filters",
                account = "Your account", online = "Available", away = "Away",
                availabilityHint = "Available team members can receive new assignments.",
                aiHandling = "AI is replying", assignedTo = "Assigned to", legacyHuman = "Human support",
                signOutTitle = "Sign out of this inbox?", cancel = "Cancel", signOut = "Sign out",
                reconnectTitle = "Could not connect", reconnectBody = "Your session is saved. Check your connection and try again.",
                sessionExpired = "Your session expired. Sign in again.", notificationUnavailable = "This conversation is no longer available.",
                contacts = "Contacts", connectionError = "Could not refresh. Showing the last loaded conversations.", loading = "Loading", tabTitle = "Inbox",
            ),
            list = ListCopy(
                signOut = "Sign out", emptyTitle = "No conversations yet",
                emptyBody = "When someone writes to your assistant, the conversation shows up here.",
                loadFailed = "Could not load conversations", noMessages = "No messages yet", youReply = "You reply",
                untitled = "Conversation", webVisitor = "Web visitor",
            ),
            chat = Chat(
                back = "Back", youAreReplying = "You are replying", assistantIsReplying = "The assistant is replying",
                takeOver = "Take over", handBack = "Hand back", takeOverWide = "Take over to reply yourself",
                empty = "No messages in this conversation yet.", loadFailed = "Could not load this conversation",
                modeFailed = "Could not change the mode", sendFailed = "Could not send", fileFailed = "Could not send that file",
            ),
            composer = Composer(
                placeholder = "Message", attach = "Add an attachment", send = "Send", fromLibrary = "Photo & Video Library",
                fromCamera = "Camera", sheetTitle = "Attach", cancel = "Cancel", record = "Record a voice note", recording = "Starting…",
                discard = "Cancel", discardLabel = "Delete recording", pause = "Pause recording", resume = "Resume recording",
                sendVoice = "Send voice note", cameraDeniedTitle = "Camera access is off", photosDeniedTitle = "Photo access is off",
                mediaDeniedBody = "Turn it on in Settings to send photos from here.",
                micDeniedTitle = "Microphone access is off", micDeniedBody = "Turn it on in Settings to send voice notes.",
                recordFailedTitle = "Could not start recording", recordFailedBody = "Try again in a moment.",
            ),
            attachment = AttachmentCopy(imageUnavailable = "Image unavailable", generic = "Attachment", image = "Attached image", play = "Play voice note", pause = "Pause voice note"),
            channels = Channels(whatsapp = "WhatsApp", instagram = "Instagram", messenger = "Facebook Messenger", widget = "Web chat", playground = "Playground"),
            `when` = When(today = "Today", yesterday = "Yesterday"),
            errors = Errors(
                unreachable = "Could not reach that server. Check the address and that you are on the same network.",
                generic = "Something went wrong", sendFile = "Could not send that file",
            ),
        )

        val es = Strings(
            signIn = SignIn(
                title = "Entra a tu cuenta", subtitle = "Usa el correo y la contraseña que te dio tu agencia.",
                serverLabel = "Dirección del servidor", serverPlaceholder = "chat.miagencia.com", serverHint = "La dirección de la instancia que tu agencia tiene montada.",
                otherServer = "Otro servidor", workspaceLabel = "Espacio de trabajo", workspacePlaceholder = "tu-agencia",
                workspaceHint = "Escribe el nombre de tu espacio o pega su dirección.",
                workspaceUnavailable = "Este espacio no está disponible. Revisa la dirección o contacta a tu administrador.",
                incorrectCredentials = "Correo o contraseña incorrectos. Usa tu cuenta de operador de la bandeja.",
                emailLabel = "Correo", emailPlaceholder = "tu@negocio.com", passwordLabel = "Contraseña", submit = "Entrar",
                failed = "No pudimos iniciar sesión", invalidWorkspace = "Escribe el nombre de tu espacio o su dirección HTTPS.",
                invalidServer = "Escribe una dirección de servidor válida.", connectedTo = "Estás conectado a {name}.", changeServer = "Cambiar servidor",
                useHosted = "Usar {name}", forgot = "¿Olvidaste tu contraseña?", forgotTitle = "Tu agencia gestiona tu acceso",
                forgotBody = "Pídele a quien te dio esta cuenta que te asigne una contraseña nueva.",
                chooseAccount = "¿Cuál cuenta?", chooseAccountBody = "Este correo abre más de una bandeja. Elige en cuál quieres trabajar.",
                serverTitle = "Conéctate a tu servidor", connect = "Continuar",
            ),
            inbox = Inbox(
                title = "Bandeja de entrada", all = "Todas", unread = "No leídas", mine = "Asignadas", ai = "IA", open = "Abiertas", resolved = "Resueltas",
                search = "Busca un nombre, teléfono o mensaje", filters = "Filtros", teams = "Equipos", allTeams = "Todos los equipos", allChannels = "Todos los canales",
                done = "Listo", retry = "Reintentar", loadingMore = "Cargando más…", loadMore = "Cargar más",
                noResults = "No hay conversaciones que coincidan", noResultsBody = "Prueba otra búsqueda o filtro.", clearFilters = "Quitar filtros",
                account = "Tu cuenta", online = "Disponible", away = "Ausente",
                availabilityHint = "Los miembros disponibles pueden recibir nuevas asignaciones.",
                aiHandling = "Responde la IA", assignedTo = "Asignado a", legacyHuman = "Atención humana",
                signOutTitle = "¿Salir de esta bandeja?", cancel = "Cancelar", signOut = "Salir",
                reconnectTitle = "No pudimos conectar", reconnectBody = "Tu sesión está guardada. Revisa la conexión e inténtalo de nuevo.",
                sessionExpired = "Tu sesión venció. Vuelve a entrar.", notificationUnavailable = "Esta conversación ya no está disponible.",
                contacts = "Contactos", connectionError = "No pudimos actualizar. Mostramos las últimas conversaciones cargadas.", loading = "Cargando", tabTitle = "Bandeja",
            ),
            list = ListCopy(
                signOut = "Salir", emptyTitle = "Todavía no hay conversaciones",
                emptyBody = "Cuando alguien le escriba a tu asistente, la conversación aparece aquí.",
                loadFailed = "No pudimos cargar las conversaciones", noMessages = "Sin mensajes todavía", youReply = "Respondes tú",
                untitled = "Conversación", webVisitor = "Visitante web",
            ),
            chat = Chat(
                back = "Atrás", youAreReplying = "Estás respondiendo tú", assistantIsReplying = "Está respondiendo el asistente",
                takeOver = "Tomar", handBack = "Devolver", takeOverWide = "Toma la conversación para responder tú",
                empty = "Esta conversación todavía no tiene mensajes.", loadFailed = "No pudimos cargar esta conversación",
                modeFailed = "No pudimos cambiar el modo", sendFailed = "No se pudo enviar", fileFailed = "No se pudo enviar ese archivo",
            ),
            composer = Composer(
                placeholder = "Mensaje", attach = "Adjuntar", send = "Enviar", fromLibrary = "Fotos y videos",
                fromCamera = "Cámara", sheetTitle = "Adjuntar", cancel = "Cancelar", record = "Grabar una nota de voz", recording = "Empezando…",
                discard = "Cancelar", discardLabel = "Borrar la grabación", pause = "Pausar la grabación", resume = "Seguir grabando",
                sendVoice = "Enviar la nota de voz", cameraDeniedTitle = "La cámara está bloqueada", photosDeniedTitle = "Las fotos están bloqueadas",
                mediaDeniedBody = "Actívalo en Ajustes para poder enviar fotos desde aquí.",
                micDeniedTitle = "El micrófono está bloqueado", micDeniedBody = "Actívalo en Ajustes para poder enviar notas de voz.",
                recordFailedTitle = "No pudimos empezar a grabar", recordFailedBody = "Inténtalo de nuevo en un momento.",
            ),
            attachment = AttachmentCopy(imageUnavailable = "La imagen no está disponible", generic = "Adjunto", image = "Imagen adjunta", play = "Reproducir la nota de voz", pause = "Pausar la nota de voz"),
            channels = Channels(whatsapp = "WhatsApp", instagram = "Instagram", messenger = "Facebook Messenger", widget = "Chat web", playground = "Pruebas"),
            `when` = When(today = "Hoy", yesterday = "Ayer"),
            errors = Errors(
                unreachable = "No pudimos llegar a ese servidor. Revisa la dirección y que estés en la misma red.",
                generic = "Algo salió mal", sendFile = "No se pudo enviar ese archivo",
            ),
        )
    }
}
