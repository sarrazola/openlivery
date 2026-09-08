/** Typed conversation copy, selected using the device language. */
const en = {
  ai: "AI", details: "Conversation details", close: "Close", retry: "Try again", cancel: "Cancel", save: "Save", done: "Done",
  open: "Open", resolved: "Resolved", resolve: "Resolve conversation", resolveTitle: "Resolve this conversation?",
  resolveHint: "This case will become read-only. The contact’s next message starts a new case.",
  resolvedHint: "This case is resolved. The contact’s next message starts a new conversation.",
  resolveConfirm: "Resolve", assignee: "Assigned to", unassigned: "Unassigned", team: "Team", noTeam: "No team", me: "You",
  contact: "Contact", name: "Name", phone: "Phone", email: "Email", notes: "Contact notes", notesHint: "Visible to your team. These notes are not sent to the contact.",
  noContact: "No linked contact", history: "Previous conversations", noHistory: "No other conversations", information: "Information", agent: "Assistant", visitor: "Contact",
  windowClosed: "WhatsApp reply window closed", windowHint: "Send an approved template to reach this contact. Free-form replies are available for 24 hours after they write.",
  sendTemplate: "Send template", templates: "Approved templates", noTemplates: "No approved templates are available. Create and submit one from the inbox on the web.",
  templateValue: "Value", preview: "Preview", send: "Send", chooseTemplate: "Choose a template", actions: "Message actions",
  quote: "Reply to message", quoting: "Replying to", cancelQuote: "Cancel quoted reply", unavailableQuote: "Earlier message", react: "React", removeReaction: "Remove reaction",
  sent: "Sent", delivered: "Delivered", read: "Read", pending: "Sending", failed: "Delivery failed", activity: "Conversation activity", someone: "Someone",
  loadFailed: "Could not load conversation details", updateFailed: "Could not update this conversation", newMessages: "New messages", latest: "Go to latest message",
  shared: "Shared content", noMedia: "No attachments yet", canned: "Saved replies", noCanned: "No saved replies yet. Create them in the inbox on the web.", searchReplies: "Search saved replies",
  file: "Choose a file", removeFile: "Remove attachment", attachmentFailed: "Could not open this attachment", attachmentRetry: "Download again", shareUnavailable: "Opening files is unavailable on this device", audioFailed: "Could not load audio", openFile: "Open attachment", viewImage: "View full image", caption: "Add a caption", attached: "Ready to send", pickFailed: "Could not select that file", recordFailed: "Could not finish recording. Try again.",
  notifications: "Updates are paused while the app is in the background.",
  recordAudio: "Record audio", reviewAudio: "Stop and review audio", review: "Review", audioReady: "Audio message",
  micUnavailable: "The microphone is unavailable. Open the app directly on your phone and check microphone access in Settings.", recordingTooShort: "Recording is too short. Try again.",
  events: {
    resolved: "{actor} resolved the conversation", reopened: "{actor} reopened the conversation", reopened_by_contact: "The contact wrote again",
    taken_over: "{actor} took over the conversation", returned_to_ai: "{actor} returned the conversation to the assistant",
    auto_resolved: "Resolved automatically after {hours} h without activity", self_assigned: "{actor} is now handling the conversation",
    assigned: "{actor} assigned the conversation to {assignee}", transferred: "{actor} transferred the conversation to {assignee}", unassigned: "{actor} released the conversation",
    started: "{actor} started the conversation", team_assigned: "{actor} moved the conversation to {team}", team_removed: "{actor} removed the conversation from {team}", escalated: "{actor} escalated to {target}: {reason}",
  },
};
const es: typeof en = {
  ai: "IA", details: "Detalles de la conversación", close: "Cerrar", retry: "Reintentar", cancel: "Cancelar", save: "Guardar", done: "Listo",
  open: "Abierta", resolved: "Resuelta", resolve: "Resolver conversación", resolveTitle: "¿Resolver esta conversación?",
  resolveHint: "Este caso quedará cerrado. El siguiente mensaje del contacto iniciará un caso nuevo.",
  resolvedHint: "Este caso está resuelto. El siguiente mensaje del contacto iniciará una conversación nueva.",
  resolveConfirm: "Resolver", assignee: "Responsable", unassigned: "Sin asignar", team: "Equipo", noTeam: "Sin equipo", me: "Tú",
  contact: "Contacto", name: "Nombre", phone: "Teléfono", email: "Correo", notes: "Notas del contacto", notesHint: "Visibles para tu equipo. Estas notas no se envían al contacto.",
  noContact: "Sin contacto vinculado", history: "Conversaciones anteriores", noHistory: "No hay otras conversaciones", information: "Información", agent: "Asistente", visitor: "Contacto",
  windowClosed: "La ventana de WhatsApp está cerrada", windowHint: "Envía una plantilla aprobada para contactar a esta persona. Puedes responder libremente durante 24 horas después de que te escriba.",
  sendTemplate: "Enviar plantilla", templates: "Plantillas aprobadas", noTemplates: "No hay plantillas aprobadas. Crea y envía una a revisión desde la bandeja en la web.",
  templateValue: "Valor", preview: "Vista previa", send: "Enviar", chooseTemplate: "Elige una plantilla", actions: "Acciones del mensaje",
  quote: "Responder al mensaje", quoting: "Respondiendo a", cancelQuote: "Cancelar respuesta citada", unavailableQuote: "Mensaje anterior", react: "Reaccionar", removeReaction: "Quitar reacción",
  sent: "Enviado", delivered: "Entregado", read: "Leído", pending: "Enviando", failed: "Error de entrega", activity: "Actividad de la conversación", someone: "Alguien",
  loadFailed: "No se pudieron cargar los detalles", updateFailed: "No se pudo actualizar esta conversación", newMessages: "Mensajes nuevos", latest: "Ir al último mensaje",
  shared: "Contenido compartido", noMedia: "Todavía no hay adjuntos", canned: "Respuestas guardadas", noCanned: "Todavía no hay respuestas guardadas. Créalas desde la bandeja en la web.", searchReplies: "Buscar respuestas guardadas",
  file: "Elegir un archivo", removeFile: "Quitar adjunto", attachmentFailed: "No se pudo abrir este adjunto", attachmentRetry: "Descargar de nuevo", shareUnavailable: "Este dispositivo no permite abrir archivos", audioFailed: "No se pudo cargar el audio", openFile: "Abrir adjunto", viewImage: "Ver imagen completa", caption: "Añade un mensaje", attached: "Listo para enviar", pickFailed: "No se pudo seleccionar ese archivo", recordFailed: "No se pudo terminar la grabación. Inténtalo de nuevo.",
  notifications: "Las actualizaciones se pausan cuando la aplicación está en segundo plano.",
  recordAudio: "Grabar audio", reviewAudio: "Detener y revisar audio", review: "Revisar", audioReady: "Mensaje de audio",
  micUnavailable: "El micrófono no está disponible. Abre la app directamente en tu teléfono y revisa el acceso al micrófono en Ajustes.", recordingTooShort: "La grabación es demasiado corta. Inténtalo de nuevo.",
  events: {
    resolved: "{actor} resolvió la conversación", reopened: "{actor} reabrió la conversación", reopened_by_contact: "El contacto volvió a escribir",
    taken_over: "{actor} tomó la conversación", returned_to_ai: "{actor} devolvió la conversación al asistente",
    auto_resolved: "Resuelta automáticamente tras {hours} h sin actividad", self_assigned: "{actor} está atendiendo la conversación",
    assigned: "{actor} asignó la conversación a {assignee}", transferred: "{actor} transfirió la conversación a {assignee}", unassigned: "{actor} liberó la conversación",
    started: "{actor} inició la conversación", team_assigned: "{actor} movió la conversación a {team}", team_removed: "{actor} quitó la conversación de {team}", escalated: "{actor} escaló a {target}: {reason}",
  },
};
export type ChatStrings = typeof en;
export function chatStrings(): ChatStrings {
  try {
    const { getLocales } = require("expo-localization") as typeof import("expo-localization");
    return getLocales()[0]?.languageCode === "es" ? es : en;
  } catch { return en; }
}
export function activityLabel(message: { content: string; sender_name?: string | null; activity?: Record<string, unknown> | null }, s: ChatStrings): string {
  const event = String(message.activity?.event || "");
  const template = s.events[event as keyof typeof s.events];
  if (!template) return message.content;
  const vars = { ...message.activity, actor: message.sender_name || s.someone };
  return template.replace(/\{(\w+)\}/g, (_, key: string) => String(vars[key as keyof typeof vars] ?? ""));
}
