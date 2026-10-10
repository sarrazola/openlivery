package com.example.inbox.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.inbox.AppModel
import com.example.inbox.api.ApiException
import com.example.inbox.api.Availability
import com.example.inbox.api.PortalApi
import com.example.inbox.api.PortalMember
import com.example.inbox.api.Team
import com.example.inbox.api.TeamUpdate
import com.example.inbox.localization.WorkspaceStrings
import com.example.inbox.rules.Conversations
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.launch

/** Teams, people and your own availability. */
@OptIn(androidx.compose.foundation.layout.ExperimentalLayoutApi::class)
@Composable
fun TeamsPanel(model: AppModel, onEdit: (Team?) -> Unit) {
    val s = WorkspaceStrings.current
    val accent = LocalAccent.current
    val palette = accent.palette
    val session = model.session ?: return
    val server = model.server
    val canManage = session.has("teams.manage")
    var teams by remember { mutableStateOf<List<Team>>(emptyList()) }
    var members by remember { mutableStateOf<List<PortalMember>>(emptyList()) }
    var loading by remember { mutableStateOf(true) }
    var error by remember { mutableStateOf<String?>(null) }
    var availabilityBusy by remember { mutableStateOf(false) }
    var reload by remember { mutableIntStateOf(0) }
    val scope = rememberCoroutineScope()

    LaunchedEffect(reload) {
        try {
            teams = PortalApi.teams(server, session)
            members = PortalApi.members(server, session)
            error = null
        } catch (failure: CancellationException) { throw failure }
        catch (failure: ApiException) { if (failure.isUnauthorized) model.expireSession(); error = failure.message }
        catch (failure: Exception) { error = s.loadFailed }
        loading = false
    }

    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(20.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        error?.let { ErrorNotice(it, s.retry) { reload += 1 } }
        Row(verticalAlignment = Alignment.CenterVertically) {
            SectionTitle(s.teams, Modifier.weight(1f))
            if (canManage) Text("+ ${s.newTeam}", color = accent.color, fontSize = 14.sp, modifier = Modifier.clip(RoundedCornerShape(12.dp)).background(accent.tint()).clickable { onEdit(null) }.padding(11.dp))
        }
        if (loading) ContactsSkeleton(com.example.inbox.localization.Strings.current.inbox.loading, rows = 3)
        else if (teams.isEmpty()) Card {
            Text(s.noTeams, color = palette.ink, fontWeight = FontWeight.SemiBold)
            Text(if (canManage) s.noTeamsHint else s.noTeamsReadOnlyHint, color = palette.muted, fontSize = 14.sp)
        }
        teams.forEach { team ->
            Box(Modifier.clickable(enabled = canManage) { onEdit(team) }) {
                Card {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        Text(team.name, color = palette.ink, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f))
                        if (team.isDefault) Text(s.defaultTeam, color = accent.color, fontSize = 10.sp, modifier = Modifier.clip(RoundedCornerShape(6.dp)).background(accent.tint()).padding(horizontal = 7.dp, vertical = 4.dp))
                    }
                    if (team.description.isNotEmpty()) Text(team.description, color = palette.muted, fontSize = 14.sp)
                    Text("${if (team.strategy == "least_busy") s.leastBusy else s.roundRobin} · ${team.openCount} ${s.open}" + (if (team.unassignedCount > 0) " · ${team.unassignedCount} ${s.unassigned}" else ""), color = palette.muted, fontSize = 12.sp)
                    if (team.members.isEmpty()) Text(s.noMembers, color = palette.muted)
                    else FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        team.members.forEach { member -> Chip(member.name.ifEmpty { member.email }, if (member.availability == Availability.ONLINE) Theme.onlineGreen else palette.subtle) }
                    }
                }
            }
        }
        SectionTitle(s.people, Modifier.padding(top = 22.dp))
        members.forEach { member ->
            Row(Modifier.fillMaxWidth().padding(vertical = 10.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                CircleDot(if (member.availability == Availability.ONLINE) Theme.onlineGreen else palette.subtle, 7.dp)
                Column(Modifier.weight(1f)) {
                    Text(member.name.ifEmpty { member.email } + (if (member.id == session.userId) " · ${s.me}" else ""), color = palette.ink, fontWeight = FontWeight.SemiBold)
                    Text(if (member.availability == Availability.ONLINE) s.online else s.away, color = palette.muted, fontSize = 12.sp)
                }
                if (member.id == session.userId) {
                    Text(if (member.availability == Availability.ONLINE) s.goAway else s.goOnline, color = accent.color, fontSize = 12.sp, modifier = Modifier.clickable(enabled = !availabilityBusy) {
                        scope.launch {
                            availabilityBusy = true
                            try {
                                val updated = PortalApi.setAvailability(server, session, if (member.availability == Availability.ONLINE) Availability.AWAY else Availability.ONLINE)
                                members = members.map { if (it.id == updated.id) updated else it }
                                teams = teams.map { team -> team.copy(members = team.members.map { if (it.id == updated.id) updated else it }) }
                            } catch (failure: Exception) { error = (failure as? ApiException)?.message ?: s.loadFailed }
                            availabilityBusy = false
                        }
                    }.padding(8.dp))
                }
            }
            Line()
        }
        Spacer(Modifier.height(20.dp))
    }
}

/** Create or edit a team: name, description, strategy, members, channels and the default flag. */
@Composable
fun TeamEditor(model: AppModel, team: Team?, onDone: () -> Unit) {
    val s = WorkspaceStrings.current
    val accent = LocalAccent.current
    val palette = accent.palette
    val session = model.session ?: return
    val server = model.server
    var name by remember { mutableStateOf(team?.name ?: "") }
    var description by remember { mutableStateOf(team?.description ?: "") }
    var strategy by remember { mutableStateOf(team?.strategy ?: "round_robin") }
    var channels by remember { mutableStateOf<List<String>>(team?.channels ?: emptyList()) }
    var memberIds by remember { mutableStateOf<List<String>>(team?.members?.map { it.id } ?: emptyList()) }
    var isDefault by remember { mutableStateOf(team?.isDefault ?: false) }
    var members by remember { mutableStateOf<List<PortalMember>>(emptyList()) }
    var saving by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    val scope = rememberCoroutineScope()

    LaunchedEffect(Unit) { members = runCatching { PortalApi.members(server, session) }.getOrDefault(emptyList()) }

    Column(Modifier.fillMaxSize().imePadding()) {
        TopBar(if (team == null) s.newTeam else s.editTeam, s.cancel, onBack = { if (!saving) onDone() })
        Line()
        Column(Modifier.weight(1f).verticalScroll(rememberScrollState()).padding(20.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            error?.let { Text(it, color = palette.danger) }
            FieldLabel(s.teamName)
            FormTextField(name, { name = it }, enabled = !saving)
            FieldLabel(s.description)
            FormTextField(description, { description = it }, multiline = true, enabled = !saving)
            FieldLabel(s.strategy)
            ChoiceRow(s.roundRobin, s.roundRobinHint, strategy == "round_robin", enabled = !saving) { strategy = "round_robin" }
            ChoiceRow(s.leastBusy, s.leastBusyHint, strategy == "least_busy", enabled = !saving) { strategy = "least_busy" }
            FieldLabel(s.members)
            if (members.isEmpty()) Text(s.noMembers, color = palette.muted)
            members.forEach { member ->
                ChoiceRow(member.name.ifEmpty { member.email }, if (member.availability == Availability.ONLINE) s.online else s.away, member.id in memberIds, checkbox = true, enabled = !saving) {
                    memberIds = if (member.id in memberIds) memberIds - member.id else memberIds + member.id
                }
            }
            FieldLabel(s.channels)
            Text(s.channelHint, color = palette.muted, fontSize = 12.sp)
            teamChannels.forEach { channel ->
                Row(Modifier.fillMaxWidth().padding(vertical = 4.dp), verticalAlignment = Alignment.CenterVertically) {
                    Text(Conversations.channelName(channel), color = palette.ink, modifier = Modifier.weight(1f))
                    Switch(checked = channel in channels, onCheckedChange = { channels = if (channel in channels) channels - channel else channels + channel }, enabled = !saving,
                        colors = SwitchDefaults.colors(checkedTrackColor = accent.color))
                }
            }
            Row(Modifier.fillMaxWidth().padding(top = 12.dp), verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text(s.defaultTeam, color = palette.ink, fontWeight = FontWeight.SemiBold)
                    Text(s.defaultHint, color = palette.muted, fontSize = 12.sp)
                }
                Spacer(Modifier.width(8.dp))
                Switch(checked = isDefault, onCheckedChange = { isDefault = it }, enabled = !saving, colors = SwitchDefaults.colors(checkedTrackColor = accent.color))
            }
            Spacer(Modifier.height(16.dp))
            PrimaryButton(s.save, enabled = name.isNotBlank(), busy = saving) {
                scope.launch {
                    saving = true; error = null
                    try {
                        val payload = TeamUpdate(name.trim(), description.trim(), strategy, channels, isDefault, memberIds)
                        if (team != null) PortalApi.updateTeam(server, session, team.id, payload) else PortalApi.createTeam(server, session, payload)
                        onDone()
                    } catch (failure: ApiException) {
                        if (failure.isUnauthorized) model.expireSession()
                        error = if (failure.status == 409) s.duplicateName else failure.message
                    } catch (failure: Exception) { error = s.saveFailed }
                    saving = false
                }
            }
            Spacer(Modifier.height(20.dp))
        }
    }
}
