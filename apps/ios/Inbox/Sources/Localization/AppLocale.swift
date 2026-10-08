import Foundation

/// English and Spanish, chosen by the phone.
///
/// There is no language picker on purpose: someone answering their business's
/// messages should not have to set one, and the phone already knows. Anything
/// the device is not set to falls back to English.
enum AppLocale {
    static var languageCode: String {
        let preferred = Locale.preferredLanguages.first ?? "en"
        let code = Locale(identifier: preferred).language.languageCode?.identifier ?? "en"
        return code.lowercased() == "es" ? "es" : "en"
    }

    static var isSpanish: Bool { languageCode == "es" }

    static func pick<T>(_ en: T, _ es: T) -> T { isSpanish ? es : en }
}
