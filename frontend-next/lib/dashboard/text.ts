/** Small wording helpers for the briefing sentences. Plain TypeScript. */

const WORDS = ["no", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"];

/** "one" ... "nine"; digits from 10. 0 reads as "no". */
export function numberWord(n: number): string {
  return n >= 0 && n < 10 && Number.isInteger(n) ? WORDS[n] : String(n);
}

export function capitalizeFirst(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

/** Lower-cases only the first letter, so names inside the sentence
 * ("Telangana High Court", "Respondent No.2") keep their capitals. */
export function lowerFirst(text: string): string {
  return text.charAt(0).toLowerCase() + text.slice(1);
}

/** "1 case", "5 cases". */
export function countOf(n: number, singular: string, plural = `${singular}s`): string {
  return `${n} ${n === 1 ? singular : plural}`;
}

/** Shortens `text` to about `max` characters at a word boundary. */
export function clip(text: string, max: number): string {
  const clean = text.replace(/\s+/g, " ").trim();
  if (clean.length <= max) return clean;
  const cut = clean.slice(0, max);
  const space = cut.lastIndexOf(" ");
  return `${(space > max * 0.6 ? cut.slice(0, space) : cut).replace(/[\s,.;:]+$/, "")}…`;
}

/** Drops a closing full stop so the text can sit inside a sentence. */
export function withoutFinalStop(text: string): string {
  return text.trim().replace(/[.\s]+$/, "");
}
