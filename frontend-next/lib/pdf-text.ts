/** Text search inside a PDF page, from pdf.js text items.
 *
 * Kept free of pdf.js itself so it can be tested with plain objects: the
 * viewer hands it each page's text items and gets back where the query sits,
 * as rectangles in the page's own (scale 1) pixels. */

/** The parts of a pdf.js TextItem this needs. */
export interface TextItemLite {
  str: string;
  /** [a, b, c, d, e, f] in PDF user space. */
  transform: number[];
  /** Advance width in user space. */
  width: number;
  hasEOL?: boolean;
}

export type Matrix = [number, number, number, number, number, number];

/** m1 x m2, the way pdf.js composes a text item's matrix with the viewport's. */
export function multiplyMatrix(m1: readonly number[], m2: readonly number[]): Matrix {
  return [
    m1[0] * m2[0] + m1[2] * m2[1],
    m1[1] * m2[0] + m1[3] * m2[1],
    m1[0] * m2[2] + m1[2] * m2[3],
    m1[1] * m2[2] + m1[3] * m2[3],
    m1[0] * m2[4] + m1[2] * m2[5] + m1[4],
    m1[1] * m2[4] + m1[3] * m2[5] + m1[5],
  ];
}

export interface PageMatch {
  /** Which occurrence of the query this piece belongs to (0-based). An
   * occurrence that spans two text items is two pieces with one number. */
  occurrence: number;
  /** Which text item the piece falls in. */
  item: number;
  /** Character range within that item's string. */
  from: number;
  to: number;
}

/** Every occurrence of `query` on a page (case-insensitive).
 *
 * Items are joined into one string so a phrase that pdf.js split across two
 * items is still found; an item that ends a line contributes a space. A match
 * is reported once per item it touches, each with its own character range. */
export function findPageMatches(items: readonly TextItemLite[], query: string): PageMatch[] {
  const needle = query.trim().toLowerCase();
  if (!needle) return [];

  const starts: number[] = [];
  let text = "";
  for (const item of items) {
    starts.push(text.length);
    text += item.str;
    if (item.hasEOL && !/\s$/.test(item.str)) text += " ";
  }
  const haystack = text.toLowerCase();

  const matches: PageMatch[] = [];
  let occurrence = 0;
  let at = haystack.indexOf(needle);
  while (at !== -1) {
    const end = at + needle.length;
    for (let i = 0; i < items.length; i++) {
      const itemStart = starts[i];
      const itemEnd = itemStart + items[i].str.length;
      if (itemEnd <= at || itemStart >= end) continue;
      matches.push({
        occurrence,
        item: i,
        from: Math.max(at, itemStart) - itemStart,
        to: Math.min(end, itemEnd) - itemStart,
      });
    }
    occurrence += 1;
    at = haystack.indexOf(needle, end);
  }
  return matches;
}

export interface HighlightRect {
  x: number;
  y: number;
  width: number;
  height: number;
}

/** A match as a rectangle in the page's scale-1 pixels, for an overlay.
 *
 * The share of the item's width is proportional to the characters matched,
 * which is exact for a monospaced run and close enough for a highlight. */
export function matchRect(
  item: TextItemLite,
  match: PageMatch,
  viewportTransform: readonly number[],
): HighlightRect {
  const tx = multiplyMatrix(viewportTransform, item.transform);
  const fontHeight = Math.hypot(tx[2], tx[3]);
  const length = Math.max(item.str.length, 1);
  const scaleX = Math.hypot(viewportTransform[0], viewportTransform[1]);
  const itemWidth = item.width * scaleX;
  return {
    x: tx[4] + (match.from / length) * itemWidth,
    y: tx[5] - fontHeight,
    width: ((match.to - match.from) / length) * itemWidth,
    height: fontHeight * 1.15,
  };
}
