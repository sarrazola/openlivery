package com.example.inbox.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.inbox.rules.DialCodes

/**
 * A phone input the way the web has it: a country with its flag and dial code,
 * then the national number. The value handed back is the full digits-only number.
 */
@OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class)
@Composable
fun PhoneField(phone: String, enabled: Boolean = true, searchPlaceholder: String, onChange: (String) -> Unit) {
    val accent = LocalAccent.current
    val palette = accent.palette
    val initial = remember { DialCodes.split(phone) }
    var iso by remember { mutableStateOf(initial?.first ?: DialCodes.defaultCountry) }
    var national by remember { mutableStateOf(initial?.second ?: phone.filter { it.isDigit() }) }
    var picking by remember { mutableStateOf(false) }
    var query by remember { mutableStateOf("") }

    fun compose(nextIso: String, nextNational: String) {
        val digits = nextNational.filter { it.isDigit() }
        iso = nextIso; national = digits
        onChange(if (digits.isEmpty()) "" else DialCodes.dialCode(nextIso) + digits)
    }

    Row(
        Modifier.fillMaxWidth().height(50.dp).clip(RoundedCornerShape(14.dp)).background(palette.canvas),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Row(Modifier.fillMaxHeight().clickable(enabled = enabled) { picking = true }.padding(horizontal = 12.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
            Text(DialCodes.flag(iso), fontSize = 20.sp)
            Text("▾", color = palette.muted, fontSize = 11.sp)
        }
        Box(Modifier.width(0.5.dp).height(28.dp).background(palette.line))
        Text("+${DialCodes.dialCode(iso)}", color = palette.muted, fontSize = 16.sp, modifier = Modifier.padding(start = 12.dp, end = 8.dp))
        BasicTextField(
            value = national, onValueChange = { compose(iso, it) }, enabled = enabled, singleLine = true,
            textStyle = TextStyle(color = palette.ink, fontSize = 16.sp), cursorBrush = SolidColor(accent.color),
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Phone),
            modifier = Modifier.weight(1f).padding(end = 12.dp),
        )
    }

    if (picking) {
        val rows = DialCodes.sortedByName.filter { query.isBlank() || it.name.contains(query, ignoreCase = true) || it.code.startsWith(query.trimStart('+')) }
        ModalBottomSheet(onDismissRequest = { picking = false; query = "" }, containerColor = palette.surface) {
            Column(Modifier.padding(horizontal = 16.dp).padding(bottom = 20.dp)) {
                SearchField(query, searchPlaceholder, { query = it })
                Spacer(Modifier.height(8.dp))
                LazyColumn(Modifier.fillMaxWidth().height(420.dp)) {
                    items(rows, key = { it.iso }) { country ->
                        Row(
                            Modifier.fillMaxWidth().clickable { compose(country.iso, national); picking = false; query = "" }.padding(vertical = 12.dp),
                            verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp),
                        ) {
                            Text(country.flag, fontSize = 20.sp)
                            Text(country.name, color = palette.ink, modifier = Modifier.weight(1f), fontWeight = if (country.iso == iso) FontWeight.SemiBold else FontWeight.Normal)
                            Text("+${country.code}", color = palette.muted)
                        }
                        Line()
                    }
                }
            }
        }
    }
}
