package com.example.inbox.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.inbox.AppModel
import com.example.inbox.api.ApiException
import com.example.inbox.api.PortalApi
import com.example.inbox.api.PortalReport
import com.example.inbox.api.Team
import com.example.inbox.localization.WorkspaceStrings
import com.example.inbox.rules.Conversations
import com.example.inbox.rules.Reports
import kotlinx.coroutines.CancellationException

val teamChannels = listOf("whatsapp", "whatsapp_cloud", "instagram", "messenger", "widget")

/** Operational reports, for the people whose role may see them. */
@Composable
fun ReportsScreen(model: AppModel) {
    val s = WorkspaceStrings.current
    val accent = LocalAccent.current
    val palette = accent.palette
    val session = model.session ?: return
    val server = model.server
    var days by remember { mutableIntStateOf(7) }
    var channel by remember { mutableStateOf("") }
    var team by remember { mutableStateOf("") }
    var teams by remember { mutableStateOf<List<Team>>(emptyList()) }
    var report by remember { mutableStateOf<PortalReport?>(null) }
    var loading by remember { mutableStateOf(true) }
    var error by remember { mutableStateOf<String?>(null) }
    var reload by remember { mutableIntStateOf(0) }
    val range = Reports.range(days)

    if (!session.has("reports.view")) {
        PlaceholderScreen(s.reports, s.noAccess)
        return
    }

    LaunchedEffect(days, channel, team, reload) {
        loading = true; report = null; error = null
        if (teams.isEmpty()) teams = runCatching { PortalApi.teams(server, session) }.getOrDefault(emptyList())
        try {
            report = PortalApi.report(server, session, range.copy(channel = channel.ifEmpty { null }, teamId = team.ifEmpty { null }))
        } catch (failure: CancellationException) {
            throw failure
        } catch (failure: ApiException) {
            if (failure.isUnauthorized) model.expireSession()
            error = failure.message
        } catch (failure: Exception) {
            error = s.loadFailed
        }
        loading = false
    }

    Column(Modifier.fillMaxSize().statusBarsPadding().verticalScroll(rememberScrollState()).padding(horizontal = 18.dp)) {
        Text(s.reports, color = palette.ink, fontSize = 28.sp, fontWeight = FontWeight.Bold, modifier = Modifier.padding(top = 18.dp))
        Text(s.reportsSubtitle, color = palette.muted, fontSize = 13.sp, modifier = Modifier.padding(bottom = 14.dp))
        Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).background(palette.canvas).padding(3.dp)) {
            listOf(7 to s.days7, 30 to s.days30, 90 to s.days90).forEach { (value, label) ->
                Box(
                    Modifier.weight(1f).height(32.dp).clip(RoundedCornerShape(8.dp)).background(if (days == value) palette.surface else androidx.compose.ui.graphics.Color.Transparent).clickable { days = value },
                    contentAlignment = Alignment.Center,
                ) { Text(label, color = palette.ink, fontSize = 14.sp, fontWeight = if (days == value) FontWeight.SemiBold else FontWeight.Normal) }
            }
        }
        Row(Modifier.fillMaxWidth().padding(top = 10.dp), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            FilterMenu(if (channel.isEmpty()) s.channels else Conversations.channelName(channel), channel.isNotEmpty(), Modifier.weight(1f),
                options = listOf("" to s.allChannels) + teamChannels.map { it to Conversations.channelName(it) }) { channel = it }
            if (teams.isNotEmpty()) {
                FilterMenu(if (team.isEmpty()) s.teams else teams.firstOrNull { it.id == team }?.name ?: s.teams, team.isNotEmpty(), Modifier.weight(1f),
                    options = listOf("" to s.allTeams) + teams.map { it.id to it.name }) { team = it }
            }
        }
        Text("${Reports.dayLabel(range.from)} – ${Reports.dayLabel(range.to)} · ${Reports.utcLabel(range.tzOffset)}", color = palette.muted, fontSize = 12.sp, modifier = Modifier.padding(vertical = 10.dp))
        error?.let { ErrorNotice(it, s.retry) { reload += 1 } }
        if (loading) {
            Sheen(com.example.inbox.localization.Strings.current.inbox.loading) {
                Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    repeat(3) { Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) { SkeletonBlock(height = 94.dp, radius = 16.dp); } }
                }
            }
        } else report?.let { r ->
            val metrics = listOf(
                s.started to r.started.toString(), s.resolved to r.resolved.toString(), s.openNow to r.openNow.toString(), s.agentsOnline to r.agentsOnline.toString(),
                s.inbound to r.inboundMessages.toString(), s.humanReplies to r.humanReplies.toString(), s.aiReplies to r.aiReplies.toString(), s.activeContacts to r.activeContacts.toString(),
                s.firstReply to Reports.duration(r.avgFirstReplySeconds, s), s.resolutionTime to Reports.duration(r.avgResolutionSeconds, s),
            )
            metrics.chunked(2).forEach { pair ->
                Row(Modifier.fillMaxWidth().padding(bottom = 10.dp), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    pair.forEach { (label, value) ->
                        Column(Modifier.weight(1f).height(94.dp).clip(RoundedCornerShape(16.dp)).background(palette.raised).padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                            Text(value, color = palette.ink, fontSize = 22.sp, fontWeight = FontWeight.Bold)
                            Text(label, color = palette.muted, fontSize = 12.sp)
                        }
                    }
                    if (pair.size == 1) Spacer(Modifier.weight(1f))
                }
            }
            Text(s.currentHint, color = palette.muted, fontSize = 12.sp)
            Text(s.averageHint, color = palette.muted, fontSize = 12.sp, modifier = Modifier.padding(top = 4.dp))
            SectionTitle(s.daily, Modifier.padding(top = 24.dp, bottom = 10.dp))
            if (r.started == 0 && r.resolved == 0) Text(s.noActivity, color = palette.muted, fontSize = 14.sp)
            else DailyBars(r, accent.color, Theme.onlineGreen)
            SectionTitle(s.channelActivity, Modifier.padding(top = 24.dp, bottom = 6.dp))
            if (r.byChannel.isEmpty()) Text(s.noActivity, color = palette.muted)
            r.byChannel.forEach { row ->
                Row(Modifier.fillMaxWidth().padding(vertical = 12.dp), verticalAlignment = Alignment.CenterVertically) {
                    Text(Conversations.channelName(row.channel), color = palette.ink, modifier = Modifier.weight(1f))
                    Text(row.started.toString(), color = accent.color, fontWeight = FontWeight.SemiBold)
                }
                Line()
            }
            SectionTitle(s.teamActivity, Modifier.padding(top = 24.dp, bottom = 10.dp))
            r.byAgent.forEach { member ->
                Box(Modifier.padding(bottom = 10.dp)) {
                    Card {
                        Text(member.name.ifEmpty { s.people }, color = palette.ink, fontWeight = FontWeight.SemiBold)
                        Text("${s.replies}: ${member.replies} · ${s.assigned}: ${member.assigned} · ${s.openNow}: ${member.openNow}", color = palette.muted, fontSize = 12.sp)
                    }
                }
            }
            Spacer(Modifier.height(30.dp))
        }
    }
}

@Composable
private fun DailyBars(report: PortalReport, started: androidx.compose.ui.graphics.Color, resolved: androidx.compose.ui.graphics.Color) {
    val s = WorkspaceStrings.current
    val palette = LocalAccent.current.palette
    val days = report.byDay
    val max = (days.maxOfOrNull { maxOf(it.started, it.resolved) } ?: 1).coerceAtLeast(1)
    Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(16.dp)).background(palette.raised).padding(16.dp)) {
        Row(horizontalArrangement = Arrangement.spacedBy(14.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) { CircleDot(started, 8.dp); Text(s.started, color = palette.muted, fontSize = 12.sp) }
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) { CircleDot(resolved, 8.dp); Text(s.resolved, color = palette.muted, fontSize = 12.sp) }
        }
        Canvas(Modifier.fillMaxWidth().height(200.dp).padding(top = 12.dp)) {
            if (days.isEmpty()) return@Canvas
            val slot = size.width / days.size
            val bar = (slot * 0.36f).coerceAtMost(22f * density)
            days.forEachIndexed { index, day ->
                val x = index * slot + slot / 2
                val hs = size.height * day.started / max
                val hr = size.height * day.resolved / max
                drawRoundRect(started, Offset(x - bar - 1f, size.height - hs), Size(bar, hs), androidx.compose.ui.geometry.CornerRadius(3f))
                drawRoundRect(resolved, Offset(x + 1f, size.height - hr), Size(bar, hr), androidx.compose.ui.geometry.CornerRadius(3f))
            }
        }
        Row(Modifier.fillMaxWidth().padding(top = 6.dp), horizontalArrangement = Arrangement.SpaceBetween) {
            days.firstOrNull()?.let { Text(Reports.dayLabel(it.date), color = palette.muted, fontSize = 11.sp) }
            days.lastOrNull()?.takeIf { days.size > 1 }?.let { Text(Reports.dayLabel(it.date), color = palette.muted, fontSize = 11.sp) }
        }
    }
}

/** A dropdown that reads as a filter chip, filled when a value is chosen. */
@Composable
fun FilterMenu(label: String, active: Boolean, modifier: Modifier = Modifier, options: List<Pair<String, String>>, onPick: (String) -> Unit) {
    val accent = LocalAccent.current
    val palette = accent.palette
    var open by remember { mutableStateOf(false) }
    Box(modifier) {
        Row(
            Modifier.fillMaxWidth().height(38.dp).clip(RoundedCornerShape(19.dp)).background(if (active) accent.tint() else palette.canvas).clickable { open = true }.padding(horizontal = 12.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(label, color = if (active) accent.color else palette.ink, fontSize = 14.sp, fontWeight = FontWeight.SemiBold, maxLines = 1, modifier = Modifier.weight(1f))
            Text("▾", color = if (active) accent.color else palette.ink, fontSize = 12.sp)
        }
        DropdownMenu(expanded = open, onDismissRequest = { open = false }) {
            options.forEach { (value, text) -> DropdownMenuItem(text = { Text(text) }, onClick = { onPick(value); open = false }) }
        }
    }
    Spacer(Modifier.width(0.dp))
}
