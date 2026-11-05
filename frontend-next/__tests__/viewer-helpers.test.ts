import { describe, it, expect } from "vitest";
import { documentForOrder, orderForDocument, viewerKind } from "@/lib/viewer-source";
import { findPageMatches, matchRect, multiplyMatrix } from "@/lib/pdf-text";
import { matchDocMarkers } from "@/components/chat/chat-panel";
import type { Citation, CourtOrder, Document } from "@/types";

const doc = (overrides: Partial<Document>): Document =>
  ({
    id: 1,
    filename: "order-4.pdf",
    file_size: 1000,
    file_type: "application/pdf",
    document_type: "court_order",
    ...overrides,
  }) as Document;

const order = (overrides: Partial<CourtOrder>): CourtOrder =>
  ({
    id: 10,
    filename: "order-4.pdf",
    file_size: 1000,
    has_file: true,
    ...overrides,
  }) as CourtOrder;

describe("pairing a court-order document with its order", () => {
  it("pairs by file name and size, in both directions", () => {
    expect(orderForDocument(doc({}), [order({ id: 10 }), order({ id: 11, filename: "other.pdf" })])?.id).toBe(10);
    expect(documentForOrder(order({}), [doc({ id: 5 }), doc({ id: 6, filename: "other.pdf" })])?.id).toBe(5);
  });

  it("refuses an ambiguous pairing rather than guess", () => {
    // Two orders with the same name and size: which one is this document?
    expect(orderForDocument(doc({}), [order({ id: 10 }), order({ id: 11 })])).toBeNull();
    expect(documentForOrder(order({}), [doc({ id: 5 }), doc({ id: 6 })])).toBeNull();
  });

  it("does not pair when the size differs or the order has no file", () => {
    expect(orderForDocument(doc({}), [order({ file_size: 999 })])).toBeNull();
    expect(orderForDocument(doc({}), [order({ has_file: false })])).toBeNull();
    expect(documentForOrder(order({ filename: null }), [doc({})])).toBeNull();
  });

  it("only ever pairs a court-order document", () => {
    expect(orderForDocument(doc({ document_type: "pleading" }), [order({})])).toBeNull();
    expect(documentForOrder(order({}), [doc({ document_type: "pleading" })])).toBeNull();
  });
});

describe("viewerKind", () => {
  it("tells a PDF, an image and anything else apart", () => {
    expect(viewerKind({ filename: "a.PDF", file_type: null })).toBe("pdf");
    expect(viewerKind({ filename: "a", file_type: "application/pdf" })).toBe("pdf");
    expect(viewerKind({ filename: "scan.JPG", file_type: null })).toBe("image");
    expect(viewerKind({ filename: "scan", file_type: "image/png" })).toBe("image");
    expect(viewerKind({ filename: "notes.docx", file_type: "docx" })).toBe("other");
  });
});

describe("PDF text search", () => {
  const item = (str: string, x: number, y: number, width: number, hasEOL = false) => ({
    str,
    width,
    hasEOL,
    transform: [10, 0, 0, 10, x, y],
  });

  it("finds a phrase case-insensitively and reports the item and range", () => {
    const items = [item("The Respondent shall file", 0, 0, 100)];
    expect(findPageMatches(items, "respondent")).toEqual([{ occurrence: 0, item: 0, from: 4, to: 14 }]);
    expect(findPageMatches(items, "  ")).toEqual([]);
    expect(findPageMatches(items, "absent")).toEqual([]);
  });

  it("finds every occurrence, and a phrase split across two items", () => {
    const items = [item("counter ", 0, 0, 10), item("affidavit and counter", 10, 0, 10)];
    expect(findPageMatches(items, "counter")).toEqual([
      { occurrence: 0, item: 0, from: 0, to: 7 },
      { occurrence: 1, item: 1, from: 14, to: 21 },
    ]);
    expect(findPageMatches(items, "counter affidavit")).toEqual([
      { occurrence: 0, item: 0, from: 0, to: 8 },
      { occurrence: 0, item: 1, from: 0, to: 9 },
    ]);
  });

  it("treats the end of a line as a space between words", () => {
    const items = [item("file", 0, 0, 10, true), item("counter", 0, 12, 10)];
    const matches = findPageMatches(items, "file counter");
    expect(matches).toHaveLength(2);
    expect(new Set(matches.map((m) => m.occurrence)).size).toBe(1);
  });

  it("multiplies matrices the way pdf.js composes them", () => {
    // A scale-1 viewport that flips y for a 100pt-high page.
    const viewport = [1, 0, 0, -1, 0, 100];
    expect(multiplyMatrix(viewport, [10, 0, 0, 10, 20, 30])).toEqual([10, 0, 0, -10, 20, 70]);
  });

  it("puts the highlight over the matched characters", () => {
    const viewport = [1, 0, 0, -1, 0, 100];
    const text = item("abcdefghij", 20, 30, 100); // baseline at y=70 from the top
    const rect = matchRect(text, { occurrence: 0, item: 0, from: 5, to: 10 }, viewport);
    expect(rect.x).toBeCloseTo(70); // 20 + half of 100
    expect(rect.width).toBeCloseTo(50);
    expect(rect.y).toBeCloseTo(60); // baseline 70 minus the 10px font height
    expect(rect.height).toBeGreaterThan(10);
  });
});

describe("matching [Doc N] markers to citations", () => {
  const cite = (id: number, documentId: number): Citation =>
    ({ id, document_id: documentId, chunk_id: id, citation_text: "", source_type: "chunk", created_at: "" }) as Citation;

  it("maps markers to citations in first-appearance order when counts agree", () => {
    const citations = [cite(1, 30), cite(2, 10)];
    const matched = matchDocMarkers("Held [Doc 3] and later [Doc 1], again [Doc 3].", citations);
    expect(matched.get(3)?.document_id).toBe(30);
    expect(matched.get(1)?.document_id).toBe(10);
  });

  it("links nothing when a marker was dropped server-side", () => {
    // Three distinct markers but two citations: one was out of range or a
    // duplicate passage, so the remaining ones cannot be told apart.
    expect(matchDocMarkers("[Doc 1] [Doc 2] [Doc 9]", [cite(1, 10), cite(2, 20)]).size).toBe(0);
  });

  it("links nothing for an answer without markers", () => {
    expect(matchDocMarkers("No sources here.", [cite(1, 10)]).size).toBe(0);
  });
});
