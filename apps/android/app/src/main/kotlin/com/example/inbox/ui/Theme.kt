package com.example.inbox.ui

import androidx.compose.runtime.Immutable
import androidx.compose.runtime.compositionLocalOf
import androidx.compose.ui.graphics.Color

/**
 * Colour.
 *
 * The app is white label, so the workspace's colour arrives with the session
 * and drives anything accented. Everything else is a neutral palette that has
 * to read well against any brand colour, and has to follow the phone: an app
 * that stays white when the system is dark feels like a web page in a wrapper.
 */
@Immutable
data class Palette(
    val ink: Color, val muted: Color, val subtle: Color, val line: Color, val surface: Color,
    /** Behind grouped content: slightly off from `surface` in both schemes. */
    val canvas: Color,
    /** Raised rows on top of `canvas`. */
    val raised: Color, val danger: Color, val bubbleIn: Color, val pressed: Color,
) {
    companion object {
        val light = Palette(
            ink = Theme.hex("#17213b"), muted = Theme.hex("#68718a"), subtle = Theme.hex("#929ab0"), line = Theme.hex("#e2e6ee"),
            surface = Color.White, canvas = Theme.hex("#e7eaf0"), raised = Color.White, danger = Theme.hex("#d95757"), bubbleIn = Color.White,
            pressed = Color.Black.copy(alpha = 0.05f),
        )
        val dark = Palette(
            ink = Theme.hex("#f2f4f8"), muted = Theme.hex("#9aa3b8"), subtle = Theme.hex("#7b8399"), line = Theme.hex("#2a2f3a"),
            surface = Theme.hex("#161a21"), canvas = Theme.hex("#0b0d11"), raised = Theme.hex("#1c212a"), danger = Theme.hex("#ff6b6b"),
            bubbleIn = Theme.hex("#262d3a"), pressed = Color.White.copy(alpha = 0.07f),
        )
        fun current(dark: Boolean) = if (dark) Palette.dark else light
    }
}

object Theme {
    const val defaultBrand = "#2f3a4a"
    val whatsappGreen = hex("#16834b")
    val onlineGreen = hex("#16a571")
    val resolvedGreen = hex("#17876B")

    private fun components(value: String): Triple<Int, Int, Int>? {
        val clean = value.replace("#", "")
        if (clean.length != 6) return null
        val number = clean.toLongOrNull(16) ?: return null
        return Triple(((number shr 16) and 0xff).toInt(), ((number shr 8) and 0xff).toInt(), (number and 0xff).toInt())
    }

    fun hex(value: String): Color {
        val (r, g, b) = components(value) ?: return Color(0xFF2F3A4A)
        return Color(r, g, b)
    }

    private fun luminance(r: Int, g: Int, b: Int): Double = (0.299 * r + 0.587 * g + 0.114 * b) / 255

    /** Readable text colour for a filled brand-coloured surface. */
    fun contrastOn(value: String): Color {
        val (r, g, b) = components(value) ?: return Color.White
        return if (luminance(r, g, b) > 0.6) Palette.light.ink else Color.White
    }

    /** A brand colour that stays visible on a dark background. */
    fun accentFor(value: String, dark: Boolean): Color {
        val (r, g, b) = components(value) ?: return hex(defaultBrand)
        if (!dark) return Color(r, g, b)
        if (luminance(r, g, b) >= 0.35) return Color(r, g, b)
        val lift = { c: Int -> (c + (255 - c) * 0.45).toInt().coerceIn(0, 255) }
        return Color(lift(r), lift(g), lift(b))
    }

    fun tint(value: String, alpha: Float = 0.12f): Color = hex(value).copy(alpha = alpha)
}

/** The workspace colour and palette for every signed-in screen. */
@Immutable
data class Accent(val hex: String, val dark: Boolean) {
    val color: Color get() = Theme.accentFor(hex, dark)
    val onColor: Color get() = Theme.contrastOn(hex)
    val palette: Palette get() = Palette.current(dark)
    fun tint(alpha: Float = 0.12f): Color = color.copy(alpha = alpha)
}

val LocalAccent = compositionLocalOf { Accent(Theme.defaultBrand, false) }
