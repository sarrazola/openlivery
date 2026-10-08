import SwiftUI

/// Colour.
///
/// Two things are going on at once. The app is white label, so the workspace's
/// colour arrives with the session and drives anything accented. Everything else
/// is a neutral palette that has to read well against any brand colour, and has
/// to follow the phone: an app that stays white when the system is dark is the
/// first thing that makes it feel like a web page in a wrapper.
struct Palette {
    let ink: Color
    let muted: Color
    let subtle: Color
    let line: Color
    let surface: Color
    /// Behind grouped content: slightly off from `surface` in both schemes.
    let canvas: Color
    /// Raised rows on top of `canvas`.
    let raised: Color
    let danger: Color
    let bubbleIn: Color
    /// A press highlight that works on either scheme.
    let pressed: Color

    static let light = Palette(
        ink: Color(hex: "#17213b"), muted: Color(hex: "#68718a"), subtle: Color(hex: "#929ab0"), line: Color(hex: "#e2e6ee"),
        surface: .white, canvas: Color(hex: "#e7eaf0"), raised: .white, danger: Color(hex: "#d95757"), bubbleIn: .white,
        pressed: Color.black.opacity(0.05)
    )

    static let dark = Palette(
        ink: Color(hex: "#f2f4f8"), muted: Color(hex: "#9aa3b8"), subtle: Color(hex: "#7b8399"), line: Color(hex: "#2a2f3a"),
        surface: Color(hex: "#161a21"), canvas: Color(hex: "#0b0d11"), raised: Color(hex: "#1c212a"), danger: Color(hex: "#ff6b6b"),
        bubbleIn: Color(hex: "#262d3a"), pressed: Color.white.opacity(0.07)
    )

    static func current(_ scheme: ColorScheme) -> Palette { scheme == .dark ? dark : light }
}

enum Theme {
    static let defaultBrand = "#2f3a4a"
    static let whatsappGreen = Color(hex: "#16834b")
    static let onlineGreen = Color(hex: "#16a571")
    static let resolvedGreen = Color(hex: "#17876B")

    private static func components(_ hex: String) -> (Double, Double, Double)? {
        let value = hex.replacingOccurrences(of: "#", with: "")
        guard value.count == 6, let number = UInt32(value, radix: 16) else { return nil }
        return (Double((number >> 16) & 0xff), Double((number >> 8) & 0xff), Double(number & 0xff))
    }

    private static func luminance(_ r: Double, _ g: Double, _ b: Double) -> Double {
        (0.299 * r + 0.587 * g + 0.114 * b) / 255
    }

    /// Readable text colour for a filled brand-coloured surface.
    static func contrastOn(_ hex: String) -> Color {
        guard let (r, g, b) = components(hex) else { return .white }
        return luminance(r, g, b) > 0.6 ? Palette.light.ink : .white
    }

    /// A translucent wash of the brand colour, for selected rows and soft chips.
    static func tint(_ hex: String, _ alpha: Double = 0.12) -> Color {
        guard let (r, g, b) = components(hex) else { return Color(red: 120 / 255, green: 120 / 255, blue: 120 / 255).opacity(alpha) }
        return Color(red: r / 255, green: g / 255, blue: b / 255).opacity(alpha)
    }

    /// Lift a brand colour until it is readable on a dark background.
    ///
    /// A deep navy brand is invisible on black. Rather than dropping the
    /// workspace's colour in dark mode, it is lightened just enough to carry
    /// accent text.
    static func readableBrand(_ hex: String, isDark: Bool) -> String {
        guard isDark, var (r, g, b) = components(hex) else {
            return components(hex) == nil ? defaultBrand : hex
        }
        var guardCount = 0
        while luminance(r, g, b) < 0.45 && guardCount < 12 {
            r = min(255, (r + (255 - r) * 0.22).rounded())
            g = min(255, (g + (255 - g) * 0.22).rounded())
            b = min(255, (b + (255 - b) * 0.22).rounded())
            guardCount += 1
        }
        return String(format: "#%02x%02x%02x", Int(r), Int(g), Int(b))
    }
}

extension Color {
    init(hex: String) {
        let value = hex.replacingOccurrences(of: "#", with: "")
        guard value.count == 6, let number = UInt32(value, radix: 16) else {
            self = Color(red: 0.47, green: 0.47, blue: 0.47)
            return
        }
        self = Color(
            red: Double((number >> 16) & 0xff) / 255,
            green: Double((number >> 8) & 0xff) / 255,
            blue: Double(number & 0xff) / 255
        )
    }
}

/// The workspace colour and palette every signed-in screen reads.
struct Accent {
    let hex: String
    let palette: Palette
    var color: Color { Color(hex: hex) }
    var onColor: Color { Theme.contrastOn(hex) }
    func tint(_ alpha: Double = 0.12) -> Color { Theme.tint(hex, alpha) }

    init(brandHex: String, scheme: ColorScheme) {
        hex = Theme.readableBrand(brandHex, isDark: scheme == .dark)
        palette = Palette.current(scheme)
    }
}
