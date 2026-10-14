// Strong passwords for accounts an admin creates for someone else: upper and
// lower case letters, digits and a few symbols, at least one of each, drawn
// from the browser's cryptographic generator. Characters that read alike
// (I, l, 1, O, 0) are left out, since the password is often passed on by hand.
const UPPER = "ABCDEFGHJKLMNPQRSTUVWXYZ";
const LOWER = "abcdefghijkmnopqrstuvwxyz";
const DIGITS = "23456789";
const SYMBOLS = "@#$%&*!?";
const ALL = UPPER + LOWER + DIGITS + SYMBOLS;

/** A uniform index below `max`, rejecting the values that would bias it. */
function randomIndex(max: number): number {
  const limit = Math.floor(0x100000000 / max) * max;
  const buffer = new Uint32Array(1);
  do crypto.getRandomValues(buffer); while (buffer[0] >= limit);
  return buffer[0] % max;
}

const pick = (set: string) => set[randomIndex(set.length)];

export function generatePassword(length = 16): string {
  const chars = [pick(UPPER), pick(LOWER), pick(DIGITS), pick(SYMBOLS)];
  while (chars.length < length) chars.push(pick(ALL));
  for (let i = chars.length - 1; i > 0; i--) {
    const j = randomIndex(i + 1);
    [chars[i], chars[j]] = [chars[j], chars[i]];
  }
  return chars.join("");
}
