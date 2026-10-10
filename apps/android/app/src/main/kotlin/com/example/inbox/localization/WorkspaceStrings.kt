package com.example.inbox.localization

/** Team operations and reporting copy. */
class WorkspaceStrings(
    val title: String, val subtitle: String, val reportsSubtitle: String, val back: String, val teams: String, val reports: String, val people: String,
    val online: String, val away: String, val me: String, val changeAvailability: String, val goOnline: String, val goAway: String,
    val newTeam: String, val editTeam: String, val noTeams: String, val noTeamsHint: String, val noTeamsReadOnlyHint: String, val noMembers: String,
    val defaultTeam: String, val open: String, val unassigned: String, val teamName: String, val description: String, val strategy: String,
    val roundRobin: String, val leastBusy: String, val roundRobinHint: String, val leastBusyHint: String, val channels: String, val channelHint: String,
    val members: String, val defaultHint: String, val save: String, val cancel: String, val duplicateName: String, val saveFailed: String,
    val loadFailed: String, val retry: String, val days7: String, val days30: String, val days90: String, val seconds: String, val minutes: String,
    val hours: String, val noData: String, val noActivity: String, val allTeams: String, val allChannels: String, val web: String,
    val started: String, val resolved: String, val openNow: String, val agentsOnline: String, val inbound: String, val humanReplies: String,
    val aiReplies: String, val activeContacts: String, val firstReply: String, val resolutionTime: String, val daily: String, val channelActivity: String,
    val teamActivity: String, val replies: String, val assigned: String, val currentHint: String, val averageHint: String, val settings: String, val noAccess: String,
) {
    companion object {
        val current: WorkspaceStrings get() = AppLocale.pick(en, es)

        val en = WorkspaceStrings(
            title = "Workspace", subtitle = "Your team and its activity", reportsSubtitle = "How the inbox is doing", back = "Back", teams = "Teams", reports = "Reports", people = "People",
            online = "Online", away = "Away", me = "You", changeAvailability = "Change availability", goOnline = "Go online", goAway = "Set away",
            newTeam = "New team", editTeam = "Edit team", noTeams = "No teams yet", noTeamsHint = "Create a team to route conversations to the right people.",
            noTeamsReadOnlyHint = "Your administrator can create teams to route conversations.", noMembers = "No members", defaultTeam = "Default", open = "open", unassigned = "unassigned",
            teamName = "Team name", description = "Description", strategy = "Assignment strategy", roundRobin = "Round robin", leastBusy = "Least busy",
            roundRobinHint = "Distribute conversations between available members in turn.", leastBusyHint = "Assign the available member with the fewest open conversations.",
            channels = "Channels", channelHint = "Choose the channels this team receives automatically.", members = "Members", defaultHint = "Default team for conversations without another routing match.",
            save = "Save team", cancel = "Cancel", duplicateName = "A team with this name already exists.", saveFailed = "Could not save the team", loadFailed = "Could not load workspace data", retry = "Try again",
            days7 = "7 days", days30 = "30 days", days90 = "90 days", seconds = "s", minutes = "min", hours = "h", noData = "No data", noActivity = "No activity during this period",
            allTeams = "All teams", allChannels = "All channels", web = "Web chat",
            started = "Started", resolved = "Resolved", openNow = "Open now", agentsOnline = "People online", inbound = "Customer messages", humanReplies = "Team replies",
            aiReplies = "Assistant replies", activeContacts = "Active contacts", firstReply = "Average first reply", resolutionTime = "Average resolution time",
            daily = "Daily activity", channelActivity = "Started by channel", teamActivity = "Operator activity", replies = "Replies", assigned = "Assigned",
            currentHint = "Open now follows the selected filters. People online covers the whole workspace. Both are current totals; other figures cover the selected period.",
            averageHint = "Response and resolution times are averages. No data means no qualifying cases in the period.",
            settings = "Settings", noAccess = "Your role does not include reports.",
        )

        val es = WorkspaceStrings(
            title = "Equipo", subtitle = "Tu equipo y su actividad", reportsSubtitle = "Cómo va la bandeja", back = "Atrás", teams = "Equipos", reports = "Reportes", people = "Personas",
            online = "En línea", away = "Ausente", me = "Tú", changeAvailability = "Cambiar disponibilidad", goOnline = "Estar en línea", goAway = "Marcar ausente",
            newTeam = "Nuevo equipo", editTeam = "Editar equipo", noTeams = "Todavía no hay equipos", noTeamsHint = "Crea un equipo para dirigir las conversaciones a las personas indicadas.",
            noTeamsReadOnlyHint = "Tu administrador puede crear equipos para asignar conversaciones.", noMembers = "Sin integrantes", defaultTeam = "Predeterminado", open = "abiertas", unassigned = "sin asignar",
            teamName = "Nombre del equipo", description = "Descripción", strategy = "Asignación", roundRobin = "Por turnos", leastBusy = "Menor carga",
            roundRobinHint = "Reparte las conversaciones por turnos entre los integrantes disponibles.", leastBusyHint = "Asigna al integrante disponible con menos conversaciones abiertas.",
            channels = "Canales", channelHint = "Elige los canales que este equipo recibe automáticamente.", members = "Integrantes", defaultHint = "Equipo predeterminado para conversaciones sin otra regla de asignación.",
            save = "Guardar equipo", cancel = "Cancelar", duplicateName = "Ya existe un equipo con este nombre.", saveFailed = "No pudimos guardar el equipo", loadFailed = "No pudimos cargar los datos del equipo", retry = "Reintentar",
            days7 = "7 días", days30 = "30 días", days90 = "90 días", seconds = "s", minutes = "min", hours = "h", noData = "Sin datos", noActivity = "No hay actividad durante este período",
            allTeams = "Todos los equipos", allChannels = "Todos los canales", web = "Chat web",
            started = "Iniciadas", resolved = "Resueltas", openNow = "Abiertas ahora", agentsOnline = "Personas en línea", inbound = "Mensajes de clientes", humanReplies = "Respuestas del equipo",
            aiReplies = "Respuestas del asistente", activeContacts = "Contactos activos", firstReply = "Primera respuesta promedio", resolutionTime = "Resolución promedio",
            daily = "Actividad diaria", channelActivity = "Iniciadas por canal", teamActivity = "Actividad por persona", replies = "Respuestas", assigned = "Asignadas",
            currentHint = "Abiertas ahora respeta los filtros. Personas en línea incluye todo el equipo. Ambas son cifras actuales; las demás corresponden al período seleccionado.",
            averageHint = "Los tiempos de respuesta y resolución son promedios. Sin datos significa que no hay casos aplicables en el período.",
            settings = "Ajustes", noAccess = "Tu rol no incluye los reportes.",
        )
    }
}
