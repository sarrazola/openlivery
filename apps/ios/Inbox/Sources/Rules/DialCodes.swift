import Foundation

/// Country calling codes for the phone input: ISO 3166-1 alpha-2 to dial code.
/// Names come from the phone's locale and the flag is the emoji the ISO code
/// maps to, so no assets are needed.
enum DialCodes {
    struct Country: Identifiable, Hashable {
        let iso: String
        let code: String
        var id: String { iso }
        var flag: String { DialCodes.flag(iso) }
        var name: String { DialCodes.name(iso) }
    }

    // Ordered by ISO code; countries sharing a dial code (1, 7, 44...) are all
    // present and `split` prefers the entry listed in `sharedPreference`.
    static let countries: [Country] = [
        ("AD", "376"), ("AE", "971"), ("AF", "93"), ("AG", "1268"), ("AI", "1264"), ("AL", "355"), ("AM", "374"), ("AO", "244"), ("AR", "54"),
        ("AS", "1684"), ("AT", "43"), ("AU", "61"), ("AW", "297"), ("AZ", "994"), ("BA", "387"), ("BB", "1246"), ("BD", "880"), ("BE", "32"),
        ("BF", "226"), ("BG", "359"), ("BH", "973"), ("BI", "257"), ("BJ", "229"), ("BM", "1441"), ("BN", "673"), ("BO", "591"), ("BR", "55"),
        ("BS", "1242"), ("BT", "975"), ("BW", "267"), ("BY", "375"), ("BZ", "501"), ("CA", "1"), ("CD", "243"), ("CF", "236"), ("CG", "242"),
        ("CH", "41"), ("CI", "225"), ("CK", "682"), ("CL", "56"), ("CM", "237"), ("CN", "86"), ("CO", "57"), ("CR", "506"), ("CU", "53"),
        ("CV", "238"), ("CW", "599"), ("CY", "357"), ("CZ", "420"), ("DE", "49"), ("DJ", "253"), ("DK", "45"), ("DM", "1767"), ("DO", "1809"),
        ("DZ", "213"), ("EC", "593"), ("EE", "372"), ("EG", "20"), ("ER", "291"), ("ES", "34"), ("ET", "251"), ("FI", "358"), ("FJ", "679"),
        ("FM", "691"), ("FO", "298"), ("FR", "33"), ("GA", "241"), ("GB", "44"), ("GD", "1473"), ("GE", "995"), ("GF", "594"), ("GH", "233"),
        ("GI", "350"), ("GL", "299"), ("GM", "220"), ("GN", "224"), ("GP", "590"), ("GQ", "240"), ("GR", "30"), ("GT", "502"), ("GU", "1671"),
        ("GW", "245"), ("GY", "592"), ("HK", "852"), ("HN", "504"), ("HR", "385"), ("HT", "509"), ("HU", "36"), ("ID", "62"), ("IE", "353"),
        ("IL", "972"), ("IN", "91"), ("IQ", "964"), ("IR", "98"), ("IS", "354"), ("IT", "39"), ("JM", "1876"), ("JO", "962"), ("JP", "81"),
        ("KE", "254"), ("KG", "996"), ("KH", "855"), ("KI", "686"), ("KM", "269"), ("KN", "1869"), ("KP", "850"), ("KR", "82"), ("KW", "965"),
        ("KY", "1345"), ("KZ", "7"), ("LA", "856"), ("LB", "961"), ("LC", "1758"), ("LI", "423"), ("LK", "94"), ("LR", "231"), ("LS", "266"),
        ("LT", "370"), ("LU", "352"), ("LV", "371"), ("LY", "218"), ("MA", "212"), ("MC", "377"), ("MD", "373"), ("ME", "382"), ("MG", "261"),
        ("MH", "692"), ("MK", "389"), ("ML", "223"), ("MM", "95"), ("MN", "976"), ("MO", "853"), ("MQ", "596"), ("MR", "222"), ("MS", "1664"),
        ("MT", "356"), ("MU", "230"), ("MV", "960"), ("MW", "265"), ("MX", "52"), ("MY", "60"), ("MZ", "258"), ("NA", "264"), ("NC", "687"),
        ("NE", "227"), ("NG", "234"), ("NI", "505"), ("NL", "31"), ("NO", "47"), ("NP", "977"), ("NR", "674"), ("NZ", "64"), ("OM", "968"),
        ("PA", "507"), ("PE", "51"), ("PF", "689"), ("PG", "675"), ("PH", "63"), ("PK", "92"), ("PL", "48"), ("PR", "1787"), ("PS", "970"),
        ("PT", "351"), ("PW", "680"), ("PY", "595"), ("QA", "974"), ("RE", "262"), ("RO", "40"), ("RS", "381"), ("RU", "7"), ("RW", "250"),
        ("SA", "966"), ("SB", "677"), ("SC", "248"), ("SD", "249"), ("SE", "46"), ("SG", "65"), ("SI", "386"), ("SK", "421"), ("SL", "232"),
        ("SM", "378"), ("SN", "221"), ("SO", "252"), ("SR", "597"), ("SS", "211"), ("ST", "239"), ("SV", "503"), ("SX", "1721"), ("SY", "963"),
        ("SZ", "268"), ("TC", "1649"), ("TD", "235"), ("TG", "228"), ("TH", "66"), ("TJ", "992"), ("TL", "670"), ("TM", "993"), ("TN", "216"),
        ("TO", "676"), ("TR", "90"), ("TT", "1868"), ("TV", "688"), ("TW", "886"), ("TZ", "255"), ("UA", "380"), ("UG", "256"), ("US", "1"),
        ("UY", "598"), ("UZ", "998"), ("VC", "1784"), ("VE", "58"), ("VG", "1284"), ("VI", "1340"), ("VN", "84"), ("VU", "678"), ("WS", "685"),
        ("YE", "967"), ("ZA", "27"), ("ZM", "260"), ("ZW", "263"),
    ].map { Country(iso: $0.0, code: $0.1) }

    // When several countries share a dial code, splitting an existing number
    // cannot tell them apart; pick the most common owner of the code.
    private static let sharedPreference: [String: String] = ["1": "US", "7": "RU", "44": "GB", "61": "AU", "212": "MA", "262": "RE", "590": "GP", "599": "CW"]

    private static let byLength: [Country] = countries.sorted { $0.code.count > $1.code.count }

    /// The emoji flag for an ISO code (regional indicator pair).
    static func flag(_ iso: String) -> String {
        String(String.UnicodeScalarView(iso.uppercased().unicodeScalars.compactMap { UnicodeScalar(0x1F1A5 + $0.value) }))
    }

    /// The country's name in the phone's language, falling back to the ISO code.
    static func name(_ iso: String) -> String {
        Locale.current.localizedString(forRegionCode: iso) ?? iso
    }

    static func country(_ iso: String) -> Country? { countries.first { $0.iso == iso } }

    static func dialCode(_ iso: String) -> String { country(iso)?.code ?? "" }

    /// Countries sorted by their localized name, for the picker.
    static var sortedByName: [Country] { countries.sorted { $0.name.localizedCaseInsensitiveCompare($1.name) == .orderedAscending } }

    /// Best-effort split of a stored digits-only number into country and national
    /// part, matching the longest dial code (preferring the code's main country).
    static func split(_ phone: String) -> (iso: String, national: String)? {
        let digits = phone.filter(\.isNumber)
        guard !digits.isEmpty else { return nil }
        for entry in byLength where digits.hasPrefix(entry.code) {
            let preferred = sharedPreference[entry.code].flatMap { country($0) }?.iso ?? entry.iso
            return (preferred, String(digits.dropFirst(entry.code.count)))
        }
        return nil
    }

    /// Default country for new numbers: the phone's region when its dial code is
    /// known, otherwise Colombia.
    static var defaultCountry: String {
        if let region = Locale.current.region?.identifier, country(region) != nil { return region }
        return "CO"
    }

    /// Groups a national number for reading: 3043682170 becomes 304 368 2170.
    private static func groupNational(_ digits: String) -> String {
        var groups: [String] = []
        var rest = Substring(digits)
        while rest.count > 4 {
            groups.append(String(rest.prefix(3)))
            rest = rest.dropFirst(3)
        }
        if !rest.isEmpty { groups.append(String(rest)) }
        return groups.joined(separator: " ")
    }

    /// Human display of a stored number: flag, dial code and grouped national part.
    static func format(_ phone: String?) -> String {
        guard let phone, !phone.isEmpty else { return "" }
        let digits = phone.filter(\.isNumber)
        guard let parts = split(digits) else { return "+\(digits)" }
        return "\(flag(parts.iso)) +\(dialCode(parts.iso)) \(groupNational(parts.national))".trimmingCharacters(in: .whitespaces)
    }
}
