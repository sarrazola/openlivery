package com.example.inbox.localization

/** Privacy disclosure and consent copy. */
class PrivacyStrings(
    val title: String, val intro: String, val reviewIntro: String, val account: String, val storedTitle: String, val stored: String,
    val aiTitle: String, val ai: String, val notificationsTitle: String, val notifications: String, val destinationsTitle: String,
    val noDestinations: String, val aiKind: String, val integrationKind: String, val notificationKind: String,
    val capabilities: Map<String, String>, val consent: String, val accept: String, val decline: String, val withdraw: String,
    val withdrawTitle: String, val withdrawBody: String, val cancel: String, val back: String, val policy: String, val support: String,
    val linkFailed: String, val actionFailed: String, val unavailable: String, val permissionRequired: String,
) {
    fun capability(key: String): String = capabilities[key] ?: key.replace("_", " ")

    companion object {
        val current: PrivacyStrings get() = AppLocale.pick(en, es)

        val en = PrivacyStrings(
            title = "Privacy and data", intro = "Before you open your workspace", reviewIntro = "Review how this workspace handles your information.",
            account = "Your workspace", storedTitle = "Information stored in the workspace",
            stored = "Your organization stores account identity, contacts, conversations and the photos, audio, videos and files you upload. Your activity in the app is associated with your operator account.",
            aiTitle = "AI and connected services",
            ai = "The workspace may send message text, conversation history, photos and audio to its configured AI services. This can include processing while a human is handling a conversation. Connected messaging channels and integrations may also receive conversation information to provide their services.",
            notificationsTitle = "Optional notifications",
            notifications = "If you enable notifications, the configured notification service receives a device token or identifier and may receive message previews to deliver alerts. You can manage notification permission in your phone's Settings.",
            destinationsTitle = "Configured destinations", noDestinations = "No external destinations are listed by this workspace.",
            aiKind = "AI service", integrationKind = "Connected service", notificationKind = "Notification service",
            capabilities = mapOf("conversation" to "Conversation text and history", "image" to "Photos", "audio" to "Audio", "integration" to "Conversation information", "messages" to "Messages", "uploads" to "Uploaded files", "notifications" to "Device identifier and notification previews"),
            consent = "By choosing Accept and continue, you consent to the processing described here and the transfer of information to the configured services. Only continue if you are authorized to use this workspace.",
            accept = "Accept and continue", decline = "Decline and sign out", withdraw = "Withdraw consent and sign out", withdrawTitle = "Withdraw consent?",
            withdrawBody = "This signs you out of this app. Existing workspace data and connected services remain managed by your organization.",
            cancel = "Cancel", back = "Back", policy = "Privacy policy", support = "Support", linkFailed = "Could not open the link. Try again.",
            actionFailed = "Could not complete this action. Try again.",
            unavailable = "This server did not provide privacy details. Ask your administrator to update it or contact support before continuing.",
            permissionRequired = "Review and accept the workspace's privacy information before continuing.",
        )

        val es = PrivacyStrings(
            title = "Privacidad y datos", intro = "Antes de abrir tu espacio de trabajo", reviewIntro = "Revisa cómo este espacio de trabajo trata tu información.",
            account = "Tu espacio de trabajo", storedTitle = "Información guardada en el espacio",
            stored = "Tu organización guarda la identidad de la cuenta, los contactos, las conversaciones y las fotos, audios, videos y archivos que subes. Tu actividad en la app está asociada a tu cuenta de operador.",
            aiTitle = "IA y servicios conectados",
            ai = "El espacio puede enviar textos, historial de conversaciones, fotos y audios a los servicios de IA que tiene configurados. Esto puede incluir procesamiento mientras una persona atiende la conversación. Los canales de mensajería y las integraciones conectadas también pueden recibir información de las conversaciones para prestar sus servicios.",
            notificationsTitle = "Notificaciones opcionales",
            notifications = "Si activas las notificaciones, el servicio configurado recibe un token o identificador del dispositivo y puede recibir vistas previas de mensajes para entregar las alertas. Puedes gestionar este permiso en los ajustes de tu teléfono.",
            destinationsTitle = "Destinos configurados", noDestinations = "Este espacio no indica destinos externos configurados.",
            aiKind = "Servicio de IA", integrationKind = "Servicio conectado", notificationKind = "Servicio de notificaciones",
            capabilities = mapOf("conversation" to "Textos e historial de conversaciones", "image" to "Fotos", "audio" to "Audio", "integration" to "Información de conversaciones", "messages" to "Mensajes", "uploads" to "Archivos subidos", "notifications" to "Identificador del dispositivo y vistas previas de notificaciones"),
            consent = "Al elegir Aceptar y continuar, das tu consentimiento para el tratamiento descrito aquí y la transferencia de información a los servicios configurados. Continúa solo si tienes autorización para utilizar este espacio de trabajo.",
            accept = "Aceptar y continuar", decline = "Rechazar y cerrar sesión", withdraw = "Retirar consentimiento y salir", withdrawTitle = "¿Retirar tu consentimiento?",
            withdrawBody = "Se cerrará tu sesión en esta app. Tu organización seguirá gestionando los datos existentes del espacio y sus servicios conectados.",
            cancel = "Cancelar", back = "Atrás", policy = "Política de privacidad", support = "Soporte", linkFailed = "No pudimos abrir el enlace. Inténtalo de nuevo.",
            actionFailed = "No pudimos completar la acción. Inténtalo de nuevo.",
            unavailable = "Este servidor no proporcionó información de privacidad. Pide a tu administrador que lo actualice o contacta a soporte antes de continuar.",
            permissionRequired = "Revisa y acepta la información de privacidad de tu espacio antes de continuar.",
        )
    }
}
