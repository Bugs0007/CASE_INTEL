import type { Document } from "@/types";

export type SortKey = "name" | "date" | "size";
export type SortDir = "asc" | "desc";
export type GroupBy = "none" | "case";

export type DocCase = NonNullable<Document["case"]>;

export interface DocumentGroup {
  /** "none" for documents with no case, else the case id. */
  key: string;
  case: DocCase | null;
  documents: Document[];
}

export function docName(doc: Document): string {
  return doc.display_name || doc.filename;
}

/** The date shown for a document: its own date, else when it was uploaded. */
export function docDate(doc: Document): string {
  return doc.document_date || doc.created_at;
}

function time(value: string): number {
  const t = Date.parse(value);
  return Number.isNaN(t) ? 0 : t;
}

export function sortDocuments(docs: Document[], key: SortKey, dir: SortDir): Document[] {
  const sign = dir === "asc" ? 1 : -1;
  return [...docs].sort((a, b) => {
    let diff = 0;
    if (key === "name") diff = docName(a).localeCompare(docName(b), undefined, { sensitivity: "base", numeric: true });
    else if (key === "size") diff = (a.file_size ?? 0) - (b.file_size ?? 0);
    else diff = time(docDate(a)) - time(docDate(b));
    return diff * sign || a.id - b.id;
  });
}

/** Documents grouped by case. Groups run newest-document first; documents
 * with no case form the last group. Order inside a group is the caller's
 * (already sorted) order. */
export function groupByCase(docs: Document[]): DocumentGroup[] {
  const groups = new Map<string, DocumentGroup & { latest: number }>();
  for (const doc of docs) {
    const key = doc.case ? String(doc.case.id) : "none";
    let group = groups.get(key);
    if (!group) {
      group = { key, case: doc.case ?? null, documents: [], latest: 0 };
      groups.set(key, group);
    }
    group.documents.push(doc);
    group.latest = Math.max(group.latest, time(docDate(doc)));
  }
  return [...groups.values()]
    .sort((a, b) => {
      if (a.key === "none") return 1;
      if (b.key === "none") return -1;
      return b.latest - a.latest;
    })
    .map(({ key, case: c, documents }) => ({ key, case: c, documents }));
}

/** The distinct cases that have documents, for the case filter. */
export function casesOf(docs: Document[]): DocCase[] {
  const seen = new Map<number, DocCase>();
  for (const doc of docs) if (doc.case && !seen.has(doc.case.id)) seen.set(doc.case.id, doc.case);
  return [...seen.values()].sort((a, b) => a.title.localeCompare(b.title, undefined, { sensitivity: "base" }));
}

export function matchesCaseQuery(c: DocCase, query: string): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  return c.title.toLowerCase().includes(q) || c.case_number.toLowerCase().includes(q);
}
