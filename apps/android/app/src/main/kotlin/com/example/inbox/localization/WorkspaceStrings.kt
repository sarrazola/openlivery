package com.example.inbox.localization

/** Workspace tab copy: team directory, availability and reports. */
class WorkspaceStrings(
    val title: String, val reports: String, val team: String, val web: String, val noData: String, val online: String, val away: String,
    val settings: String, val members: String, val availability: String,
) {
    companion object {
        val current: WorkspaceStrings get() = AppLocale.pick(en, es)
        val en = WorkspaceStrings(title = "Workspace", reports = "Reports", team = "Team", web = "Web chat", noData = "No data", online = "Available", away = "Away", settings = "Settings", members = "Members", availability = "Availability")
        val es = WorkspaceStrings(title = "Espacio", reports = "Reportes", team = "Equipo", web = "Chat web", noData = "Sin datos", online = "Disponible", away = "Ausente", settings = "Ajustes", members = "Integrantes", availability = "Disponibilidad")
    }
}
