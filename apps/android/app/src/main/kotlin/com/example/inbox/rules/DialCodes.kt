package com.example.inbox.rules

import java.util.Locale

/**
 * Country calling codes for the phone input: ISO 3166-1 alpha-2 to dial code.
 * Names come from the phone's locale and the flag is the emoji the ISO code
 * maps to, so no assets are needed.
 */
object DialCodes {
    data class Country(val iso: String, val code: String) {
        val flag: String get() = flag(iso)
        val name: String get() = name(iso)
    }

    private const val TABLE = "AD,376 AE,971 AF,93 AG,1268 AI,1264 AL,355 AM,374 AO,244 AR,54 AS,1684 AT,43 AU,61 AW,297 AZ,994 BA,387 BB,1246 BD,880 BE,32 " +
        "BF,226 BG,359 BH,973 BI,257 BJ,229 BM,1441 BN,673 BO,591 BR,55 BS,1242 BT,975 BW,267 BY,375 BZ,501 CA,1 CD,243 CF,236 CG,242 CH,41 CI,225 CK,682 " +
        "CL,56 CM,237 CN,86 CO,57 CR,506 CU,53 CV,238 CW,599 CY,357 CZ,420 DE,49 DJ,253 DK,45 DM,1767 DO,1809 DZ,213 EC,593 EE,372 EG,20 ER,291 ES,34 " +
        "ET,251 FI,358 FJ,679 FM,691 FO,298 FR,33 GA,241 GB,44 GD,1473 GE,995 GF,594 GH,233 GI,350 GL,299 GM,220 GN,224 GP,590 GQ,240 GR,30 GT,502 " +
        "GU,1671 GW,245 GY,592 HK,852 HN,504 HR,385 HT,509 HU,36 ID,62 IE,353 IL,972 IN,91 IQ,964 IR,98 IS,354 IT,39 JM,1876 JO,962 JP,81 KE,254 KG,996 " +
        "KH,855 KI,686 KM,269 KN,1869 KP,850 KR,82 KW,965 KY,1345 KZ,7 LA,856 LB,961 LC,1758 LI,423 LK,94 LR,231 LS,266 LT,370 LU,352 LV,371 LY,218 " +
        "MA,212 MC,377 MD,373 ME,382 MG,261 MH,692 MK,389 ML,223 MM,95 MN,976 MO,853 MQ,596 MR,222 MS,1664 MT,356 MU,230 MV,960 MW,265 MX,52 MY,60 " +
        "MZ,258 NA,264 NC,687 NE,227 NG,234 NI,505 NL,31 NO,47 NP,977 NR,674 NZ,64 OM,968 PA,507 PE,51 PF,689 PG,675 PH,63 PK,92 PL,48 PR,1787 PS,970 " +
        "PT,351 PW,680 PY,595 QA,974 RE,262 RO,40 RS,381 RU,7 RW,250 SA,966 SB,677 SC,248 SD,249 SE,46 SG,65 SI,386 SK,421 SL,232 SM,378 SN,221 SO,252 " +
        "SR,597 SS,211 ST,239 SV,503 SX,1721 SY,963 SZ,268 TC,1649 TD,235 TG,228 TH,66 TJ,992 TL,670 TM,993 TN,216 TO,676 TR,90 TT,1868 TV,688 TW,886 " +
        "TZ,255 UA,380 UG,256 US,1 UY,598 UZ,998 VC,1784 VE,58 VG,1284 VI,1340 VN,84 VU,678 WS,685 YE,967 ZA,27 ZM,260 ZW,263"

    val countries: List<Country> = TABLE.split(" ").map { entry -> entry.split(",").let { Country(it[0], it[1]) } }

    // When several countries share a dial code, splitting an existing number
    // cannot tell them apart; pick the most common owner of the code.
    private val sharedPreference = mapOf("1" to "US", "7" to "RU", "44" to "GB", "61" to "AU", "212" to "MA", "262" to "RE", "590" to "GP", "599" to "CW")
    private val byLength = countries.sortedByDescending { it.code.length }

    /** The emoji flag for an ISO code (regional indicator pair). */
    fun flag(iso: String): String = iso.uppercase().map { String(Character.toChars(0x1F1A5 + it.code)) }.joinToString("")

    /** The country's name in the phone's language, falling back to the ISO code. */
    fun name(iso: String): String = Locale("", iso).getDisplayCountry(Locale.getDefault()).ifEmpty { iso }

    fun country(iso: String): Country? = countries.firstOrNull { it.iso == iso }
    fun dialCode(iso: String): String = country(iso)?.code ?: ""

    /** Countries sorted by their localized name, for the picker. */
    val sortedByName: List<Country> get() = countries.sortedBy { it.name.lowercase(Locale.getDefault()) }

    /** Best-effort split of a stored digits-only number into country and national part. */
    fun split(phone: String): Pair<String, String>? {
        val digits = phone.filter { it.isDigit() }
        if (digits.isEmpty()) return null
        for (entry in byLength) if (digits.startsWith(entry.code)) {
            val preferred = sharedPreference[entry.code]?.let { country(it) }?.iso ?: entry.iso
            return preferred to digits.drop(entry.code.length)
        }
        return null
    }

    /** Default country for new numbers: the phone's region when its dial code is known, otherwise Colombia. */
    val defaultCountry: String get() = Locale.getDefault().country.takeIf { it.isNotEmpty() && country(it) != null } ?: "CO"

    /** Groups a national number for reading: 3043682170 becomes 304 368 2170. */
    private fun groupNational(digits: String): String {
        val groups = ArrayList<String>()
        var rest = digits
        while (rest.length > 4) { groups.add(rest.take(3)); rest = rest.drop(3) }
        if (rest.isNotEmpty()) groups.add(rest)
        return groups.joinToString(" ")
    }

    /** Human display of a stored number: flag, dial code and grouped national part. */
    fun format(phone: String?): String {
        if (phone.isNullOrEmpty()) return ""
        val digits = phone.filter { it.isDigit() }
        val (iso, national) = split(digits) ?: return "+$digits"
        return "${flag(iso)} +${dialCode(iso)} ${groupNational(national)}".trim()
    }
}
