/** Country calling codes for the phone input: ISO 3166-1 alpha-2 to dial
 * code. Names come from Intl.DisplayNames in the viewer's language and the
 * flag is the emoji the ISO code maps to, so no assets are needed. */

export type Country = { iso: string; code: string };

// Ordered by ISO code; countries sharing a dial code (1, 7, 44...) are all
// present and `splitPhone` prefers the entry listed in SHARED_CODE_PREFERENCE.
export const COUNTRIES: Country[] = [
  { iso: "AD", code: "376" }, { iso: "AE", code: "971" }, { iso: "AF", code: "93" },
  { iso: "AG", code: "1268" }, { iso: "AI", code: "1264" }, { iso: "AL", code: "355" },
  { iso: "AM", code: "374" }, { iso: "AO", code: "244" }, { iso: "AR", code: "54" },
  { iso: "AS", code: "1684" }, { iso: "AT", code: "43" }, { iso: "AU", code: "61" },
  { iso: "AW", code: "297" }, { iso: "AZ", code: "994" }, { iso: "BA", code: "387" },
  { iso: "BB", code: "1246" }, { iso: "BD", code: "880" }, { iso: "BE", code: "32" },
  { iso: "BF", code: "226" }, { iso: "BG", code: "359" }, { iso: "BH", code: "973" },
  { iso: "BI", code: "257" }, { iso: "BJ", code: "229" }, { iso: "BM", code: "1441" },
  { iso: "BN", code: "673" }, { iso: "BO", code: "591" }, { iso: "BR", code: "55" },
  { iso: "BS", code: "1242" }, { iso: "BT", code: "975" }, { iso: "BW", code: "267" },
  { iso: "BY", code: "375" }, { iso: "BZ", code: "501" }, { iso: "CA", code: "1" },
  { iso: "CD", code: "243" }, { iso: "CF", code: "236" }, { iso: "CG", code: "242" },
  { iso: "CH", code: "41" }, { iso: "CI", code: "225" }, { iso: "CK", code: "682" },
  { iso: "CL", code: "56" }, { iso: "CM", code: "237" }, { iso: "CN", code: "86" },
  { iso: "CO", code: "57" }, { iso: "CR", code: "506" }, { iso: "CU", code: "53" },
  { iso: "CV", code: "238" }, { iso: "CW", code: "599" }, { iso: "CY", code: "357" },
  { iso: "CZ", code: "420" }, { iso: "DE", code: "49" }, { iso: "DJ", code: "253" },
  { iso: "DK", code: "45" }, { iso: "DM", code: "1767" }, { iso: "DO", code: "1809" },
  { iso: "DZ", code: "213" }, { iso: "EC", code: "593" }, { iso: "EE", code: "372" },
  { iso: "EG", code: "20" }, { iso: "ER", code: "291" }, { iso: "ES", code: "34" },
  { iso: "ET", code: "251" }, { iso: "FI", code: "358" }, { iso: "FJ", code: "679" },
  { iso: "FM", code: "691" }, { iso: "FO", code: "298" }, { iso: "FR", code: "33" },
  { iso: "GA", code: "241" }, { iso: "GB", code: "44" }, { iso: "GD", code: "1473" },
  { iso: "GE", code: "995" }, { iso: "GF", code: "594" }, { iso: "GH", code: "233" },
  { iso: "GI", code: "350" }, { iso: "GL", code: "299" }, { iso: "GM", code: "220" },
  { iso: "GN", code: "224" }, { iso: "GP", code: "590" }, { iso: "GQ", code: "240" },
  { iso: "GR", code: "30" }, { iso: "GT", code: "502" }, { iso: "GU", code: "1671" },
  { iso: "GW", code: "245" }, { iso: "GY", code: "592" }, { iso: "HK", code: "852" },
  { iso: "HN", code: "504" }, { iso: "HR", code: "385" }, { iso: "HT", code: "509" },
  { iso: "HU", code: "36" }, { iso: "ID", code: "62" }, { iso: "IE", code: "353" },
  { iso: "IL", code: "972" }, { iso: "IN", code: "91" }, { iso: "IQ", code: "964" },
  { iso: "IR", code: "98" }, { iso: "IS", code: "354" }, { iso: "IT", code: "39" },
  { iso: "JM", code: "1876" }, { iso: "JO", code: "962" }, { iso: "JP", code: "81" },
  { iso: "KE", code: "254" }, { iso: "KG", code: "996" }, { iso: "KH", code: "855" },
  { iso: "KI", code: "686" }, { iso: "KM", code: "269" }, { iso: "KN", code: "1869" },
  { iso: "KP", code: "850" }, { iso: "KR", code: "82" }, { iso: "KW", code: "965" },
  { iso: "KY", code: "1345" }, { iso: "KZ", code: "7" }, { iso: "LA", code: "856" },
  { iso: "LB", code: "961" }, { iso: "LC", code: "1758" }, { iso: "LI", code: "423" },
  { iso: "LK", code: "94" }, { iso: "LR", code: "231" }, { iso: "LS", code: "266" },
  { iso: "LT", code: "370" }, { iso: "LU", code: "352" }, { iso: "LV", code: "371" },
  { iso: "LY", code: "218" }, { iso: "MA", code: "212" }, { iso: "MC", code: "377" },
  { iso: "MD", code: "373" }, { iso: "ME", code: "382" }, { iso: "MG", code: "261" },
  { iso: "MH", code: "692" }, { iso: "MK", code: "389" }, { iso: "ML", code: "223" },
  { iso: "MM", code: "95" }, { iso: "MN", code: "976" }, { iso: "MO", code: "853" },
  { iso: "MQ", code: "596" }, { iso: "MR", code: "222" }, { iso: "MS", code: "1664" },
  { iso: "MT", code: "356" }, { iso: "MU", code: "230" }, { iso: "MV", code: "960" },
  { iso: "MW", code: "265" }, { iso: "MX", code: "52" }, { iso: "MY", code: "60" },
  { iso: "MZ", code: "258" }, { iso: "NA", code: "264" }, { iso: "NC", code: "687" },
  { iso: "NE", code: "227" }, { iso: "NG", code: "234" }, { iso: "NI", code: "505" },
  { iso: "NL", code: "31" }, { iso: "NO", code: "47" }, { iso: "NP", code: "977" },
  { iso: "NR", code: "674" }, { iso: "NZ", code: "64" }, { iso: "OM", code: "968" },
  { iso: "PA", code: "507" }, { iso: "PE", code: "51" }, { iso: "PF", code: "689" },
  { iso: "PG", code: "675" }, { iso: "PH", code: "63" }, { iso: "PK", code: "92" },
  { iso: "PL", code: "48" }, { iso: "PR", code: "1787" }, { iso: "PS", code: "970" },
  { iso: "PT", code: "351" }, { iso: "PW", code: "680" }, { iso: "PY", code: "595" },
  { iso: "QA", code: "974" }, { iso: "RE", code: "262" }, { iso: "RO", code: "40" },
  { iso: "RS", code: "381" }, { iso: "RU", code: "7" }, { iso: "RW", code: "250" },
  { iso: "SA", code: "966" }, { iso: "SB", code: "677" }, { iso: "SC", code: "248" },
  { iso: "SD", code: "249" }, { iso: "SE", code: "46" }, { iso: "SG", code: "65" },
  { iso: "SI", code: "386" }, { iso: "SK", code: "421" }, { iso: "SL", code: "232" },
  { iso: "SM", code: "378" }, { iso: "SN", code: "221" }, { iso: "SO", code: "252" },
  { iso: "SR", code: "597" }, { iso: "SS", code: "211" }, { iso: "ST", code: "239" },
  { iso: "SV", code: "503" }, { iso: "SX", code: "1721" }, { iso: "SY", code: "963" },
  { iso: "SZ", code: "268" }, { iso: "TC", code: "1649" }, { iso: "TD", code: "235" },
  { iso: "TG", code: "228" }, { iso: "TH", code: "66" }, { iso: "TJ", code: "992" },
  { iso: "TL", code: "670" }, { iso: "TM", code: "993" }, { iso: "TN", code: "216" },
  { iso: "TO", code: "676" }, { iso: "TR", code: "90" }, { iso: "TT", code: "1868" },
  { iso: "TV", code: "688" }, { iso: "TW", code: "886" }, { iso: "TZ", code: "255" },
  { iso: "UA", code: "380" }, { iso: "UG", code: "256" }, { iso: "US", code: "1" },
  { iso: "UY", code: "598" }, { iso: "UZ", code: "998" }, { iso: "VC", code: "1784" },
  { iso: "VE", code: "58" }, { iso: "VG", code: "1284" }, { iso: "VI", code: "1340" },
  { iso: "VN", code: "84" }, { iso: "VU", code: "678" }, { iso: "WS", code: "685" },
  { iso: "YE", code: "967" }, { iso: "ZA", code: "27" }, { iso: "ZM", code: "260" },
  { iso: "ZW", code: "263" },
];

// When several countries share a dial code, splitting an existing number
// cannot tell them apart; pick the most common owner of the code.
const SHARED_CODE_PREFERENCE: Record<string, string> = { "1": "US", "7": "RU", "44": "GB", "61": "AU", "212": "MA", "262": "RE", "590": "GP", "599": "CW" };

/** The emoji flag for an ISO code (regional indicator pair). */
export function flagOf(iso: string): string {
  return String.fromCodePoint(...[...iso.toUpperCase()].map((c) => 0x1f1a5 + c.charCodeAt(0)));
}

/** The country's name in the viewer's language, falling back to the ISO code. */
export function countryName(iso: string, locale: string): string {
  try {
    return new Intl.DisplayNames([locale], { type: "region" }).of(iso) || iso;
  } catch {
    return iso;
  }
}

/** Best-effort split of a stored digits-only number into country + national
 * part, matching the longest dial code (preferring the code's main country). */
export function splitPhone(digits: string): { iso: string; national: string } | null {
  if (!digits) return null;
  const byLength = [...COUNTRIES].sort((a, b) => b.code.length - a.code.length);
  for (const entry of byLength) {
    if (digits.startsWith(entry.code)) {
      const preferred = SHARED_CODE_PREFERENCE[entry.code];
      return { iso: preferred && COUNTRIES.some((c) => c.iso === preferred) ? preferred : entry.iso, national: digits.slice(entry.code.length) };
    }
  }
  return null;
}

/** Default country for new numbers: the browser's region when we know its
 * dial code, otherwise Colombia. */
export function defaultCountry(): string {
  try {
    const region = new Intl.Locale(navigator.language).region;
    if (region && COUNTRIES.some((c) => c.iso === region)) return region;
  } catch { /* no locale information */ }
  return "CO";
}

export function dialCodeOf(iso: string): string {
  return COUNTRIES.find((c) => c.iso === iso)?.code ?? "";
}
