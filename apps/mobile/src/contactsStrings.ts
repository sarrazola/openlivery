/** Typed directory copy in the same languages as the inbox. */
const en = {
  title: "Contacts", subtitle: "People behind your conversations", search: "Search name, phone or email", newContact: "New contact",
  empty: "No contacts yet", emptyHint: "Add a contact or wait for someone to write to your inbox.", noMatches: "No matching contacts",
  back: "Back", close: "Close", cancel: "Cancel", save: "Save contact", edit: "Edit contact", name: "Name", phone: "Phone", email: "Email",
  phoneHint: "Include the country code, for example +57 300 123 4567.", invalidPhone: "Enter a valid phone number with its country code.", invalidEmail: "Enter a valid email address.",
  notes: "Contact notes", notesHint: "Visible to your team. These notes stay with the contact.", noNotes: "No notes yet", unnamed: "Contact",
  history: "Conversation history", noHistory: "No conversations yet", open: "Open", resolved: "Resolved", human: "Team", ai: "Assistant",
  start: "Start conversation", send: "Send message", chooseLine: "Choose a WhatsApp line", noLine: "No WhatsApp line is available to start a conversation.",
  message: "Message", startHint: "This sends a message to the contact and assigns the new conversation to you.",
  templateHint: "Choose an approved template to send the first message on this line.", templates: "Approved templates", noTemplates: "No approved templates are available for this line.",
  value: "Value", preview: "Preview", chooseTemplate: "Choose a template", retry: "Try again", loadFailed: "Could not load contacts", saveFailed: "Could not save this contact", sendFailed: "Could not start the conversation",
  noPhone: "Add a phone number to start a conversation.", existing: "There is already an open conversation on this line.",
  conversation: "conversation", conversations: "conversations", openCase: "open", openCases: "open", noMessages: "No messages yet", duplicatePhone: "A contact with this phone number already exists.",
};
const es: typeof en = {
  title: "Contactos", subtitle: "Las personas de tu bandeja", search: "Buscar nombre, teléfono o correo", newContact: "Nuevo contacto",
  empty: "Todavía no hay contactos", emptyHint: "Agrega un contacto o espera a que alguien escriba a tu bandeja.", noMatches: "No hay contactos que coincidan",
  back: "Atrás", close: "Cerrar", cancel: "Cancelar", save: "Guardar contacto", edit: "Editar contacto", name: "Nombre", phone: "Teléfono", email: "Correo",
  phoneHint: "Incluye el código de país, por ejemplo +57 300 123 4567.", invalidPhone: "Escribe un teléfono válido con el código de país.", invalidEmail: "Escribe un correo válido.",
  notes: "Notas del contacto", notesHint: "Visibles para tu equipo. Estas notas se guardan con el contacto.", noNotes: "Todavía no hay notas", unnamed: "Contacto",
  history: "Historial de conversaciones", noHistory: "Todavía no hay conversaciones", open: "Abierta", resolved: "Resuelta", human: "Equipo", ai: "Asistente",
  start: "Iniciar conversación", send: "Enviar mensaje", chooseLine: "Elige una línea de WhatsApp", noLine: "No hay una línea de WhatsApp disponible para iniciar una conversación.",
  message: "Mensaje", startHint: "Esto envía un mensaje al contacto y te asigna la nueva conversación.",
  templateHint: "Elige una plantilla aprobada para enviar el primer mensaje por esta línea.", templates: "Plantillas aprobadas", noTemplates: "No hay plantillas aprobadas disponibles para esta línea.",
  value: "Valor", preview: "Vista previa", chooseTemplate: "Elige una plantilla", retry: "Reintentar", loadFailed: "No pudimos cargar los contactos", saveFailed: "No pudimos guardar el contacto", sendFailed: "No pudimos iniciar la conversación",
  noPhone: "Agrega un teléfono para iniciar una conversación.", existing: "Ya existe una conversación abierta en esta línea.",
  conversation: "conversación", conversations: "conversaciones", openCase: "abierta", openCases: "abiertas", noMessages: "Sin mensajes todavía", duplicatePhone: "Ya existe un contacto con este teléfono.",
};
export type ContactsStrings = typeof en;
export function contactsStrings(): ContactsStrings {
  try {
    const { getLocales } = require("expo-localization") as typeof import("expo-localization");
    return getLocales()[0]?.languageCode === "es" ? es : en;
  } catch { return en; }
}
