// Extension point of the voice picker.
//
// A deployment can offer a set of voices to choose from, each with a short
// sample the browser plays as it is: the picker then lists them by language,
// with their accent, so choosing one asks nothing of the voice provider, and
// keeps pasting an ID from the ElevenLabs library as the way to any other
// voice. The core ships it empty, which keeps the picker on the pasted ID; a
// deployment fills it by replacing this file at build time.

export type CatalogVoice = {
  /** The voice's ID in the ElevenLabs library. */
  id: string;
  name: string;
  /** The language it speaks, as an agent's language code ("es", "en"). */
  language: string;
  /** Where its accent is from, as a region code Intl.DisplayNames names ("CO", "MX", "419" for Latin America). */
  region: string;
  gender: "female" | "male";
  /** A city or area, written as it is named, when the accent is that specific. */
  place?: string;
  /** A short sample of the voice: any URL the browser can play. */
  sample: string;
  /** The voice an agent in this language speaks with until it picks one. */
  default?: boolean;
};

export const voicePickerExtensions: {
  /** In the order the picker lists them; empty keeps the picker on the pasted ID. */
  voices: CatalogVoice[];
} = {
  voices: [],
};
