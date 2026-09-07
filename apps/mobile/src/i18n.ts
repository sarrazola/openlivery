/**
 * English and Spanish, chosen by the phone.
 *
 * There is no language picker on purpose: someone answering their business's
 * messages should not have to set one, and the phone already knows. Anything
 * the device is not set to falls back to English.
 *
 * The dictionaries are plain nested objects and `es` is typed as `typeof en`,
 * so a key that exists in one and not the other is a compile error rather than
 * a blank label someone finds in production. Strings are read as properties -
 * `s.chat.takeOver` - which means there is no lookup that can miss at runtime.
 */

const en = {
  signIn: {
    title: "Your inbox",
    subtitle: "Sign in with the details your agency gave you.",
    serverLabel: "Server address",
    serverPlaceholder: "chat.myagency.com",
    serverHint: "The address of the instance your agency runs.",
    // The hosted option's own name comes from the build's brand file; what to
    // call the alternative, and the workspace, is ordinary interface copy.
    otherServer: "Another server",
    workspaceLabel: "Agency name",
    workspacePlaceholder: "your-agency",
    emailLabel: "E-mail",
    emailPlaceholder: "you@business.com",
    passwordLabel: "Password",
    submit: "Sign in",
    failed: "Could not sign in",
    invalidWorkspace:
      "Enter the workspace name using letters, numbers or hyphens.",
    invalidServer: "Enter a valid server address.",
  },
  inbox: {
    title: "Inbox",
    all: "All",
    unread: "Unread",
    mine: "Mine",
    ai: "AI",
    open: "Open",
    resolved: "Resolved",
    search: "Search name, phone or message",
    filters: "Filters",
    teams: "Teams",
    allTeams: "All teams",
    allChannels: "All channels",
    done: "Done",
    retry: "Try again",
    loadingMore: "Loading more…",
    loadMore: "Load more",
    noResults: "No matching conversations",
    noResultsBody: "Try another search or filter.",
    clearFilters: "Clear filters",
    account: "Your account",
    online: "Available",
    away: "Away",
    availabilityHint: "Available team members can receive new assignments.",
    aiHandling: "AI is replying",
    assignedTo: "Assigned to",
    legacyHuman: "Human support",
    signOutTitle: "Sign out of this inbox?",
    cancel: "Cancel",
    signOut: "Sign out",
    reconnectTitle: "Could not connect",
    reconnectBody:
      "Your session is saved. Check your connection and try again.",
    sessionExpired: "Your session expired. Sign in again.",
    notificationUnavailable: "This conversation is no longer available.",
    contacts: "Contacts",
    connectionError:
      "Could not refresh. Showing the last loaded conversations.",
  },
  list: {
    signOut: "Sign out",
    emptyTitle: "No conversations yet",
    emptyBody:
      "When someone writes to your assistant, the conversation shows up here.",
    loadFailed: "Could not load conversations",
    noMessages: "No messages yet",
    youReply: "You reply",
    untitled: "Conversation",
    webVisitor: "Web visitor",
  },
  chat: {
    back: "Back",
    youAreReplying: "You are replying",
    assistantIsReplying: "The assistant is replying",
    takeOver: "Take over",
    handBack: "Hand back",
    takeOverWide: "Take over to reply yourself",
    empty: "No messages in this conversation yet.",
    loadFailed: "Could not load this conversation",
    modeFailed: "Could not change the mode",
    sendFailed: "Could not send",
    fileFailed: "Could not send that file",
  },
  composer: {
    placeholder: "Message",
    attach: "Add an attachment",
    send: "Send",
    fromLibrary: "Photo & Video Library",
    fromCamera: "Camera",
    sheetTitle: "Attach",
    cancel: "Cancel",
    record: "Record a voice note",
    recording: "Starting…",
    discard: "Cancel",
    discardLabel: "Delete recording",
    pause: "Pause recording",
    resume: "Resume recording",
    sendVoice: "Send voice note",
    cameraDeniedTitle: "Camera access is off",
    photosDeniedTitle: "Photo access is off",
    mediaDeniedBody: "Turn it on in Settings to send photos from here.",
    micDeniedTitle: "Microphone access is off",
    micDeniedBody: "Turn it on in Settings to send voice notes.",
    recordFailedTitle: "Could not start recording",
    recordFailedBody: "Try again in a moment.",
  },
  notifications: {
    channelName: "Messages",
  },
  attachment: {
    imageUnavailable: "Image unavailable",
    generic: "Attachment",
    image: "Attached image",
    play: "Play voice note",
    pause: "Pause voice note",
  },
  channels: {
    whatsapp: "WhatsApp",
    instagram: "Instagram",
    messenger: "Facebook Messenger",
    widget: "Web chat",
    playground: "Playground",
  },
  when: {
    today: "Today",
    yesterday: "Yesterday",
  },
  errors: {
    unreachable:
      "Could not reach that server. Check the address and that you are on the same network.",
    generic: "Something went wrong",
    sendFile: "Could not send that file",
  },
};

const es: typeof en = {
  signIn: {
    title: "Tu bandeja",
    subtitle: "Entra con los datos que te dio tu agencia.",
    serverLabel: "Dirección del servidor",
    serverPlaceholder: "chat.miagencia.com",
    serverHint: "La dirección de la instancia que tu agencia tiene montada.",
    otherServer: "Otro servidor",
    workspaceLabel: "Nombre de la agencia",
    workspacePlaceholder: "tu-agencia",
    emailLabel: "Correo",
    emailPlaceholder: "tu@negocio.com",
    passwordLabel: "Contraseña",
    submit: "Entrar",
    failed: "No pudimos iniciar sesión",
    invalidWorkspace:
      "Escribe el nombre del espacio con letras, números o guiones.",
    invalidServer: "Escribe una dirección de servidor válida.",
  },
  inbox: {
    title: "Bandeja de entrada",
    all: "Todos",
    unread: "No leídos",
    mine: "Míos",
    ai: "IA",
    open: "Abiertos",
    resolved: "Resueltos",
    search: "Busca un nombre, teléfono o mensaje",
    filters: "Filtros",
    teams: "Equipos",
    allTeams: "Todos los equipos",
    allChannels: "Todos los canales",
    done: "Listo",
    retry: "Reintentar",
    loadingMore: "Cargando más…",
    loadMore: "Cargar más",
    noResults: "No hay conversaciones que coincidan",
    noResultsBody: "Prueba otra búsqueda o filtro.",
    clearFilters: "Quitar filtros",
    account: "Tu cuenta",
    online: "Disponible",
    away: "Ausente",
    availabilityHint:
      "Los miembros disponibles pueden recibir nuevas asignaciones.",
    aiHandling: "Responde la IA",
    assignedTo: "Asignado a",
    legacyHuman: "Atención humana",
    signOutTitle: "¿Salir de esta bandeja?",
    cancel: "Cancelar",
    signOut: "Salir",
    reconnectTitle: "No pudimos conectar",
    reconnectBody:
      "Tu sesión está guardada. Revisa la conexión e inténtalo de nuevo.",
    sessionExpired: "Tu sesión venció. Vuelve a entrar.",
    notificationUnavailable: "Esta conversación ya no está disponible.",
    contacts: "Contactos",
    connectionError:
      "No pudimos actualizar. Mostramos las últimas conversaciones cargadas.",
  },
  list: {
    signOut: "Salir",
    emptyTitle: "Todavía no hay conversaciones",
    emptyBody:
      "Cuando alguien le escriba a tu asistente, la conversación aparece aquí.",
    loadFailed: "No pudimos cargar las conversaciones",
    noMessages: "Sin mensajes todavía",
    youReply: "Respondes tú",
    untitled: "Conversación",
    webVisitor: "Visitante web",
  },
  chat: {
    back: "Atrás",
    youAreReplying: "Estás respondiendo tú",
    assistantIsReplying: "Está respondiendo el asistente",
    takeOver: "Tomar",
    handBack: "Devolver",
    takeOverWide: "Toma la conversación para responder tú",
    empty: "Esta conversación todavía no tiene mensajes.",
    loadFailed: "No pudimos cargar esta conversación",
    modeFailed: "No pudimos cambiar el modo",
    sendFailed: "No se pudo enviar",
    fileFailed: "No se pudo enviar ese archivo",
  },
  composer: {
    placeholder: "Mensaje",
    attach: "Adjuntar",
    send: "Enviar",
    fromLibrary: "Fotos y videos",
    fromCamera: "Cámara",
    sheetTitle: "Adjuntar",
    cancel: "Cancelar",
    record: "Grabar una nota de voz",
    recording: "Empezando…",
    discard: "Cancelar",
    discardLabel: "Borrar la grabación",
    pause: "Pausar la grabación",
    resume: "Seguir grabando",
    sendVoice: "Enviar la nota de voz",
    cameraDeniedTitle: "La cámara está bloqueada",
    photosDeniedTitle: "Las fotos están bloqueadas",
    mediaDeniedBody: "Actívalo en Ajustes para poder enviar fotos desde aquí.",
    micDeniedTitle: "El micrófono está bloqueado",
    micDeniedBody: "Actívalo en Ajustes para poder enviar notas de voz.",
    recordFailedTitle: "No pudimos empezar a grabar",
    recordFailedBody: "Inténtalo de nuevo en un momento.",
  },
  notifications: {
    channelName: "Mensajes",
  },
  attachment: {
    imageUnavailable: "La imagen no está disponible",
    generic: "Adjunto",
    image: "Imagen adjunta",
    play: "Reproducir la nota de voz",
    pause: "Pausar la nota de voz",
  },
  channels: {
    whatsapp: "WhatsApp",
    instagram: "Instagram",
    messenger: "Facebook Messenger",
    widget: "Chat web",
    playground: "Pruebas",
  },
  when: {
    today: "Hoy",
    yesterday: "Ayer",
  },
  errors: {
    unreachable:
      "No pudimos llegar a ese servidor. Revisa la dirección y que estés en la misma red.",
    generic: "Algo salió mal",
    sendFile: "No se pudo enviar ese archivo",
  },
};

export type Strings = typeof en;

const DICTIONARIES: Record<string, Strings> = { en, es };

function pick(languageCode: string | null | undefined): Strings {
  return DICTIONARIES[(languageCode || "").toLowerCase()] || en;
}

/**
 * The dictionary for the phone's language.
 *
 * Read at call time rather than cached. Both platforms restart the app when the
 * language changes in Settings, so this is really only read once per run - but
 * reading it fresh costs nothing and means nothing can go stale.
 *
 * The localization module is required lazily because this file is also loaded
 * by scripts that run in plain Node, where no native module exists.
 */
export function strings(): Strings {
  try {
    const { getLocales } =
      require("expo-localization") as typeof import("expo-localization");
    return pick(getLocales()[0]?.languageCode);
  } catch {
    return en;
  }
}

/**
 * The same thing, named as a hook so screens read as they would with any other
 * i18n library - and so making it reactive later changes one function, not
 * every call site.
 */
export function useStrings(): Strings {
  return strings();
}
