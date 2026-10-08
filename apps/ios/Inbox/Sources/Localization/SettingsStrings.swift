import Foundation

/// Settings copy: the workspace catalogues and the account.
struct SettingsStrings {
    let title, subtitle, workspace, account, teams, tags, canned, templates, readOnly: String
    let tagsHint, newTag, editTag, tagName, tagColor, deleteTag, deleteTagBody, noTags, contacts, routesTo: String
    let cannedHint, newReply, editReply, shortcut, shortcutHint, content, variablesHint, deleteReply, deleteReplyBody, noCanned: String
    let templatesHint, newTemplate, templateName, templateNameHint, language, category, utility, marketing, body, bodyHint, footer: String
    let example, examplesHint, submit, deleteTemplate, deleteTemplateBody, noTemplates, noLine, pendingReview: String
    let save, cancel, delete, retry, loadFailed, saveFailed, duplicate, availability, signOut: String
    let header, headerNone, headerText, headerImage, headerVideo, headerDocument, headerLocation, headerTextHint, sampleHint, chooseSample, uploading: String
    let addVariable, variableName, contactVariablesHint, customVariableHint, buttons, addButton, quickReply, urlButton, phoneButton, copyCode: String
    let buttonText, buttonUrl, buttonUrlHint, buttonPhone, buttonExample, codeExample, previewTitle, previewEmpty, bold, italic, strike, code: String

    static var current: SettingsStrings { AppLocale.pick(en, es) }

    func status(_ value: String) -> String {
        switch value.uppercased() {
        case "APPROVED": return AppLocale.pick("Approved", "Aprobada")
        case "REJECTED": return AppLocale.pick("Rejected", "Rechazada")
        case "PENDING", "IN_REVIEW": return pendingReview
        case "PAUSED": return AppLocale.pick("Paused", "Pausada")
        default: return value.capitalized
        }
    }

    static let en = SettingsStrings(
        title: "Settings", subtitle: "Your workspace and your account", workspace: "Workspace", account: "Account",
        teams: "Teams", tags: "Tags", canned: "Saved replies", templates: "WhatsApp templates", readOnly: "Your administrator manages this list.",
        tagsHint: "Label contacts to find them and route their conversations.", newTag: "New tag", editTag: "Edit tag", tagName: "Name", tagColor: "Color",
        deleteTag: "Delete tag?", deleteTagBody: "The tag is removed from every contact that has it.", noTags: "No tags yet", contacts: "contacts", routesTo: "Routes to",
        cannedHint: "Type / in a conversation to insert one.", newReply: "New reply", editReply: "Edit reply", shortcut: "Shortcut",
        shortcutHint: "Lowercase letters, numbers, - and _ only.", content: "Reply",
        variablesHint: "Variables: {contact_name}, {contact_phone}, {contact_email}, {agent_name}.",
        deleteReply: "Delete saved reply?", deleteReplyBody: "It stops being offered in conversations.", noCanned: "No saved replies yet",
        templatesHint: "Approved templates reach contacts outside the 24 hour window. Meta reviews each one.", newTemplate: "New template",
        templateName: "Name", templateNameHint: "Lowercase letters, numbers and underscores.", language: "Language", category: "Category",
        utility: "Utility", marketing: "Marketing", body: "Message", bodyHint: "Use {{1}}, {{2}} for values filled when sending.", footer: "Footer",
        example: "Example for", examplesHint: "Meta reviews the template with these examples.", submit: "Submit for review",
        deleteTemplate: "Delete template?", deleteTemplateBody: "It is removed from Meta and can no longer be sent.", noTemplates: "No templates yet",
        noLine: "Connect a WhatsApp Business line on the web to use templates.", pendingReview: "In review",
        save: "Save", cancel: "Cancel", delete: "Delete", retry: "Try again", loadFailed: "Could not load", saveFailed: "Could not save",
        duplicate: "That name is already in use.", availability: "Availability", signOut: "Sign out",
        header: "Header (optional)", headerNone: "None", headerText: "Text", headerImage: "Image", headerVideo: "Video", headerDocument: "Document", headerLocation: "Location",
        headerTextHint: "Up to 60 characters, one variable at most.", sampleHint: "Meta reviews the template with this sample file.", chooseSample: "Choose a sample", uploading: "Uploading…",
        addVariable: "Add variable", variableName: "Variable name", contactVariablesHint: "Contact variables fill themselves when sending:",
        customVariableHint: "Write {{name}} where the value changes per person: lowercase and underscores.", buttons: "Buttons (optional)", addButton: "Add button",
        quickReply: "Quick reply", urlButton: "Link", phoneButton: "Call", copyCode: "Copy code",
        buttonText: "Button text", buttonUrl: "Link", buttonUrlHint: "End it with {{1}} to fill a suffix when sending.", buttonPhone: "Phone number", buttonExample: "Example suffix",
        codeExample: "Example code", previewTitle: "Preview", previewEmpty: "Start typing to see the message as WhatsApp shows it.",
        bold: "Bold", italic: "Italic", strike: "Strikethrough", code: "Code"
    )

    static let es = SettingsStrings(
        title: "Configuración", subtitle: "Tu espacio y tu cuenta", workspace: "Espacio de trabajo", account: "Cuenta",
        teams: "Equipos", tags: "Etiquetas", canned: "Respuestas guardadas", templates: "Plantillas de WhatsApp", readOnly: "Tu administrador gestiona esta lista.",
        tagsHint: "Etiqueta contactos para encontrarlos y dirigir sus conversaciones.", newTag: "Nueva etiqueta", editTag: "Editar etiqueta", tagName: "Nombre", tagColor: "Color",
        deleteTag: "¿Eliminar la etiqueta?", deleteTagBody: "Se quita de todos los contactos que la tienen.", noTags: "Todavía no hay etiquetas", contacts: "contactos", routesTo: "Dirige a",
        cannedHint: "Escribe / en una conversación para insertar una.", newReply: "Nueva respuesta", editReply: "Editar respuesta", shortcut: "Atajo",
        shortcutHint: "Solo minúsculas, números, - y _.", content: "Respuesta",
        variablesHint: "Variables: {contact_name}, {contact_phone}, {contact_email}, {agent_name}.",
        deleteReply: "¿Eliminar la respuesta guardada?", deleteReplyBody: "Deja de ofrecerse en las conversaciones.", noCanned: "Todavía no hay respuestas guardadas",
        templatesHint: "Las plantillas aprobadas llegan a contactos fuera de la ventana de 24 horas. Meta revisa cada una.", newTemplate: "Nueva plantilla",
        templateName: "Nombre", templateNameHint: "Minúsculas, números y guiones bajos.", language: "Idioma", category: "Categoría",
        utility: "Utilidad", marketing: "Marketing", body: "Mensaje", bodyHint: "Usa {{1}}, {{2}} para valores que se llenan al enviar.", footer: "Pie",
        example: "Ejemplo para", examplesHint: "Meta revisa la plantilla con estos ejemplos.", submit: "Enviar a revisión",
        deleteTemplate: "¿Eliminar la plantilla?", deleteTemplateBody: "Se elimina de Meta y ya no se puede enviar.", noTemplates: "Todavía no hay plantillas",
        noLine: "Conecta una línea de WhatsApp Business desde la web para usar plantillas.", pendingReview: "En revisión",
        save: "Guardar", cancel: "Cancelar", delete: "Eliminar", retry: "Reintentar", loadFailed: "No se pudo cargar", saveFailed: "No se pudo guardar",
        duplicate: "Ese nombre ya está en uso.", availability: "Disponibilidad", signOut: "Salir",
        header: "Encabezado (opcional)", headerNone: "Ninguno", headerText: "Texto", headerImage: "Imagen", headerVideo: "Video", headerDocument: "Documento", headerLocation: "Ubicación",
        headerTextHint: "Hasta 60 caracteres, una variable como máximo.", sampleHint: "Meta revisa la plantilla con este archivo de muestra.", chooseSample: "Elegir una muestra", uploading: "Subiendo…",
        addVariable: "Agregar variable", variableName: "Nombre de la variable", contactVariablesHint: "Variables de contacto, se completan al enviar:",
        customVariableHint: "Escribe {{nombre}} donde el valor cambia por persona: minúsculas y guiones bajos.", buttons: "Botones (opcional)", addButton: "Agregar botón",
        quickReply: "Respuesta rápida", urlButton: "Enlace", phoneButton: "Llamar", copyCode: "Copiar código",
        buttonText: "Texto del botón", buttonUrl: "Enlace", buttonUrlHint: "Termínalo en {{1}} para completar un sufijo al enviar.", buttonPhone: "Número de teléfono", buttonExample: "Sufijo de ejemplo",
        codeExample: "Código de ejemplo", previewTitle: "Vista previa", previewEmpty: "Empieza a escribir para ver el mensaje como lo muestra WhatsApp.",
        bold: "Negrita", italic: "Cursiva", strike: "Tachado", code: "Código"
    )
}
