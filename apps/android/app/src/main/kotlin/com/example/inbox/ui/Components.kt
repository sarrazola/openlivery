package com.example.inbox.ui

import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.LocalContentColor
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Text
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Search
import androidx.compose.material.icons.filled.Close
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.text.TextStyle
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.inbox.rules.Conversations

@Composable
fun Avatar(name: String, size: Dp = 48.dp, radius: Dp = 18.dp, fontSize: Int = 19) {
    val accent = LocalAccent.current
    Box(
        modifier = Modifier.size(size).clip(RoundedCornerShape(radius)).background(accent.tint()),
        contentAlignment = Alignment.Center,
    ) {
        Text(Conversations.initial(name), color = accent.color, fontSize = fontSize.sp, fontWeight = FontWeight.SemiBold)
    }
}

@Composable
fun SearchField(text: String, placeholder: String, onChange: (String) -> Unit, modifier: Modifier = Modifier) {
    val accent = LocalAccent.current
    val palette = accent.palette
    Row(
        modifier.fillMaxWidth().height(44.dp).clip(RoundedCornerShape(12.dp)).background(palette.canvas).padding(horizontal = 12.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Icon(Icons.Default.Search, contentDescription = null, tint = palette.subtle, modifier = Modifier.size(18.dp))
        Box(Modifier.weight(1f), contentAlignment = Alignment.CenterStart) {
            if (text.isEmpty()) Text(placeholder, color = palette.subtle, fontSize = 15.sp, maxLines = 1)
            BasicTextField(
                value = text, onValueChange = onChange, singleLine = true,
                textStyle = TextStyle(color = palette.ink, fontSize = 15.sp),
                cursorBrush = SolidColor(accent.color),
                modifier = Modifier.fillMaxWidth(),
            )
        }
        if (text.isNotEmpty()) Icon(Icons.Default.Close, contentDescription = null, tint = palette.subtle, modifier = Modifier.size(18.dp).clickable { onChange("") })
    }
}

@Composable
fun LabeledField(
    label: String, value: String, placeholder: String, onChange: (String) -> Unit,
    password: Boolean = false, keyboard: KeyboardType = KeyboardType.Text, enabled: Boolean = true,
) {
    val accent = LocalAccent.current
    val palette = accent.palette
    Column(modifier = Modifier.fillMaxWidth()) {
        Text(label, color = palette.ink, fontWeight = FontWeight.SemiBold, fontSize = 15.sp, modifier = Modifier.padding(bottom = 6.dp))
        OutlinedTextField(
            value = value, onValueChange = onChange, modifier = Modifier.fillMaxWidth(), singleLine = true, enabled = enabled,
            placeholder = { Text(placeholder, color = palette.subtle) },
            visualTransformation = if (password) PasswordVisualTransformation() else VisualTransformation.None,
            keyboardOptions = KeyboardOptions(keyboardType = keyboard, autoCorrectEnabled = false),
            shape = RoundedCornerShape(14.dp),
            colors = OutlinedTextFieldDefaults.colors(
                focusedContainerColor = palette.surface, unfocusedContainerColor = palette.surface,
                focusedBorderColor = accent.color, unfocusedBorderColor = palette.line,
                focusedTextColor = palette.ink, unfocusedTextColor = palette.ink, cursorColor = accent.color,
            ),
        )
    }
}

@Composable
fun PrimaryButton(label: String, enabled: Boolean = true, busy: Boolean = false, onClick: () -> Unit) {
    val accent = LocalAccent.current
    val active = enabled && !busy
    Box(
        modifier = Modifier.fillMaxWidth().height(52.dp).clip(RoundedCornerShape(14.dp))
            .background(if (active) accent.color else accent.color.copy(alpha = 0.45f))
            .clickable(enabled = active, onClick = onClick),
        contentAlignment = Alignment.Center,
    ) {
        if (busy) CircularProgressIndicator(color = accent.onColor, strokeWidth = 2.dp, modifier = Modifier.size(22.dp))
        else Text(label, color = accent.onColor, fontWeight = FontWeight.Bold, fontSize = 17.sp)
    }
}

@Composable
fun Pill(label: String, count: String? = null, selected: Boolean, modifier: Modifier = Modifier, onClick: () -> Unit) {
    val accent = LocalAccent.current
    val palette = accent.palette
    Row(
        modifier = modifier.clip(RoundedCornerShape(50)).background(if (selected) accent.tint(0.16f) else palette.canvas)
            .clickable(onClick = onClick).padding(horizontal = 14.dp, vertical = 9.dp),
        horizontalArrangement = Arrangement.Center, verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(label, color = if (selected) accent.color else palette.muted, fontWeight = FontWeight.SemiBold, fontSize = 14.sp)
        if (count != null) {
            Spacer(Modifier.width(5.dp))
            Text(count, color = if (selected) accent.color else palette.subtle, fontSize = 12.sp, fontWeight = FontWeight.Bold)
        }
    }
}

@Composable
fun ErrorNotice(message: String, retryLabel: String, onRetry: () -> Unit) {
    val palette = LocalAccent.current.palette
    Row(
        modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).background(palette.danger.copy(alpha = 0.12f))
            .clickable(onClick = onRetry).padding(12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(message, color = palette.danger, modifier = Modifier.weight(1f), fontSize = 14.sp)
        Text(retryLabel, color = palette.danger, fontWeight = FontWeight.Bold, fontSize = 14.sp)
    }
}

@Composable
fun Line() {
    Box(Modifier.fillMaxWidth().height(0.5.dp).background(LocalAccent.current.palette.line))
}

// MARK: Skeletons

@Composable
fun SkeletonBlock(width: Dp? = null, height: Dp = 12.dp, radius: Dp = 6.dp) {
    val palette = LocalAccent.current.palette
    val base = Modifier.height(height).clip(RoundedCornerShape(radius)).background(palette.line)
    Box(if (width != null) base.width(width) else base.fillMaxWidth())
}

/** Fades the placeholders in and out while they are on screen. */
@Composable
fun Sheen(label: String, content: @Composable () -> Unit) {
    val transition = rememberInfiniteTransition(label = "sheen")
    val alpha by transition.animateFloat(
        initialValue = 1f, targetValue = 0.45f,
        animationSpec = infiniteRepeatable(tween(900), RepeatMode.Reverse), label = "alpha",
    )
    Box(Modifier.alpha(alpha).semantics(mergeDescendants = true) { contentDescription = label }) { content() }
}

@Composable
fun InboxSkeleton(label: String, rows: Int = 8) {
    Sheen(label) {
        Column {
            repeat(rows) { index ->
                Row(Modifier.padding(horizontal = 20.dp, vertical = 14.dp), verticalAlignment = Alignment.Top) {
                    SkeletonBlock(48.dp, 48.dp, 18.dp)
                    Spacer(Modifier.width(13.dp))
                    Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        Row { SkeletonBlock(if (index % 2 == 0) 140.dp else 110.dp, 14.dp); Spacer(Modifier.weight(1f)); SkeletonBlock(40.dp, 10.dp) }
                        SkeletonBlock(height = 12.dp)
                        SkeletonBlock(if (index % 3 == 0) 180.dp else 120.dp, 12.dp)
                        SkeletonBlock(90.dp, 10.dp)
                    }
                }
                Box(Modifier.padding(start = 83.dp)) { Line() }
            }
        }
    }
}

@Composable
fun ChatSkeleton(label: String) {
    val palette = LocalAccent.current.palette
    Sheen(label) {
        Column(Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 12.dp), verticalArrangement = Arrangement.spacedBy(10.dp, Alignment.Bottom)) {
            listOf(Triple(220, 2, false), Triple(170, 1, true), Triple(240, 3, false), Triple(200, 2, true), Triple(150, 1, false)).forEach { (width, lines, outgoing) ->
                Row(Modifier.fillMaxWidth(), horizontalArrangement = if (outgoing) Arrangement.End else Arrangement.Start) {
                    Column(
                        Modifier.clip(RoundedCornerShape(16.dp)).background(palette.line.copy(alpha = 0.45f)).padding(12.dp),
                        verticalArrangement = Arrangement.spacedBy(6.dp),
                    ) {
                        repeat(lines) { line -> SkeletonBlock(if (line == lines - 1) (width * 0.6).dp else width.dp, 11.dp) }
                    }
                }
            }
        }
    }
}

@Composable
fun ContactsSkeleton(label: String, rows: Int = 8) {
    Sheen(label) {
        Column {
            repeat(rows) { index ->
                Row(Modifier.padding(horizontal = 20.dp, vertical = 12.dp), verticalAlignment = Alignment.CenterVertically) {
                    SkeletonBlock(48.dp, 48.dp, 18.dp)
                    Spacer(Modifier.width(12.dp))
                    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        SkeletonBlock(if (index % 2 == 0) 150.dp else 120.dp, 14.dp)
                        SkeletonBlock(180.dp, 11.dp)
                        SkeletonBlock(100.dp, 11.dp)
                    }
                }
                Box(Modifier.padding(start = 20.dp)) { Line() }
            }
        }
    }
}

@Composable
fun Centered(text: String) {
    val palette = LocalAccent.current.palette
    Box(Modifier.fillMaxWidth().padding(36.dp), contentAlignment = Alignment.Center) {
        Text(text, color = palette.muted, textAlign = TextAlign.Center)
    }
}

@Composable
fun MutedProvider(content: @Composable () -> Unit) {
    CompositionLocalProvider(LocalContentColor provides LocalAccent.current.palette.muted, content = content)
}

@Composable
fun CircleDot(color: Color, size: Dp = 10.dp) {
    Box(Modifier.size(size).clip(CircleShape).background(color))
}

@Composable
fun Outlined(modifier: Modifier = Modifier, content: @Composable () -> Unit) {
    val palette = LocalAccent.current.palette
    Box(modifier.border(1.dp, palette.line, RoundedCornerShape(10.dp))) { content() }
}

// MARK: Forms

@Composable
fun FieldLabel(text: String, modifier: Modifier = Modifier) {
    Text(text, color = LocalAccent.current.palette.ink, fontWeight = FontWeight.SemiBold, fontSize = 15.sp, modifier = modifier.padding(top = 12.dp, bottom = 6.dp))
}

@Composable
fun FormTextField(value: String, onChange: (String) -> Unit, placeholder: String = "", multiline: Boolean = false, enabled: Boolean = true, keyboard: KeyboardType = KeyboardType.Text) {
    val accent = LocalAccent.current
    val palette = accent.palette
    OutlinedTextField(
        value = value, onValueChange = onChange, modifier = Modifier.fillMaxWidth(), enabled = enabled,
        singleLine = !multiline, minLines = if (multiline) 3 else 1, maxLines = if (multiline) 8 else 1,
        placeholder = { Text(placeholder, color = palette.subtle) },
        keyboardOptions = KeyboardOptions(keyboardType = keyboard, autoCorrectEnabled = multiline),
        shape = RoundedCornerShape(14.dp),
        colors = OutlinedTextFieldDefaults.colors(
            focusedContainerColor = palette.canvas, unfocusedContainerColor = palette.canvas,
            focusedBorderColor = accent.color, unfocusedBorderColor = Color.Transparent,
            focusedTextColor = palette.ink, unfocusedTextColor = palette.ink, cursorColor = accent.color,
        ),
    )
}

/** A tappable row with a label, optional subtitle and a selected state, as a radio or a checkbox. */
@Composable
fun ChoiceRow(label: String, subtitle: String? = null, selected: Boolean, checkbox: Boolean = false, enabled: Boolean = true, onClick: () -> Unit) {
    val accent = LocalAccent.current
    val palette = accent.palette
    Row(
        Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(if (selected) accent.tint(0.1f) else palette.canvas)
            .clickable(enabled = enabled, onClick = onClick).padding(horizontal = 14.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(Modifier.weight(1f)) {
            Text(label, color = palette.ink, fontWeight = FontWeight.SemiBold, fontSize = 15.sp)
            if (!subtitle.isNullOrEmpty()) Text(subtitle, color = palette.muted, fontSize = 12.sp, maxLines = 2)
        }
        Box(
            Modifier.size(22.dp).clip(if (checkbox) RoundedCornerShape(6.dp) else CircleShape)
                .background(if (selected) accent.color else Color.Transparent)
                .border(1.5.dp, if (selected) accent.color else palette.subtle, if (checkbox) RoundedCornerShape(6.dp) else CircleShape),
            contentAlignment = Alignment.Center,
        ) { if (selected) Icon(androidx.compose.material.icons.Icons.Default.Check, null, tint = accent.onColor, modifier = Modifier.size(14.dp)) }
    }
}

@Composable
fun Card(content: @Composable androidx.compose.foundation.layout.ColumnScope.() -> Unit) {
    val palette = LocalAccent.current.palette
    Column(
        Modifier.fillMaxWidth().clip(RoundedCornerShape(16.dp)).background(palette.raised).border(0.5.dp, palette.line, RoundedCornerShape(16.dp)).padding(15.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp), content = content,
    )
}

@Composable
fun SectionTitle(text: String, modifier: Modifier = Modifier) {
    Text(text, color = LocalAccent.current.palette.ink, fontWeight = FontWeight.SemiBold, fontSize = 19.sp, modifier = modifier)
}

@Composable
fun TopBar(title: String, backLabel: String, onBack: () -> Unit, trailing: (@Composable () -> Unit)? = null) {
    val accent = LocalAccent.current
    val palette = accent.palette
    Row(Modifier.fillMaxWidth().height(52.dp).padding(horizontal = 8.dp), verticalAlignment = Alignment.CenterVertically) {
        Icon(androidx.compose.material.icons.Icons.AutoMirrored.Filled.ArrowBack, contentDescription = backLabel, tint = accent.color, modifier = Modifier.size(44.dp).clickable(onClick = onBack).padding(10.dp))
        Text(title, color = palette.ink, fontWeight = FontWeight.SemiBold, fontSize = 17.sp, modifier = Modifier.weight(1f), textAlign = TextAlign.Center)
        Box(Modifier.width(44.dp), contentAlignment = Alignment.Center) { trailing?.invoke() }
    }
}

@Composable
fun Chip(label: String, dot: Color? = null) {
    val palette = LocalAccent.current.palette
    Row(Modifier.clip(RoundedCornerShape(8.dp)).background(palette.canvas).padding(horizontal = 8.dp, vertical = 6.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        if (dot != null) CircleDot(dot, 7.dp)
        Text(label, color = palette.ink, fontSize = 12.sp)
    }
}
