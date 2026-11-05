import type { CourtOrder, Document } from "@/types";

/** Which API call serves a document's bytes.
 *
 * eCourts orders are streamed by GET /orders/<id>/file/ behind an ownership
 * check, sending the auth token. Any other document is served from storage
 * through the download endpoint, which only hands back a URL.
 *
 * A court-order Document and its CourtOrder row are one-to-one on the
 * server, but the Document the case page lists does not carry the order's
 * id, so the two are paired by file name AND size. A pairing that is not
 * unambiguous is treated as no pairing: the document then opens through the
 * storage URL, never as some other order's file. */
export function orderForDocument(
  doc: Pick<Document, "filename" | "file_size" | "document_type">,
  orders: readonly CourtOrder[],
): CourtOrder | null {
  if (doc.document_type !== "court_order") return null;
  const matches = orders.filter(
    (order) =>
      order.has_file &&
      order.filename === doc.filename &&
      order.file_size === doc.file_size,
  );
  return matches.length === 1 ? matches[0] : null;
}

/** The Document that holds an order's PDF, when it can be told apart from
 * the case's other documents. */
export function documentForOrder(
  order: Pick<CourtOrder, "filename" | "file_size">,
  documents: readonly Document[],
): Document | null {
  if (!order.filename) return null;
  const matches = documents.filter(
    (doc) =>
      doc.document_type === "court_order" &&
      doc.filename === order.filename &&
      doc.file_size === order.file_size,
  );
  return matches.length === 1 ? matches[0] : null;
}

export type ViewerKind = "pdf" | "image" | "other";

const IMAGE_EXT = /\.(png|jpe?g|gif|webp|bmp)$/i;

/** How the viewer should show a file, from what the document says it is. */
export function viewerKind(doc: Pick<Document, "filename" | "file_type">): ViewerKind {
  const type = (doc.file_type ?? "").toLowerCase();
  if (type.includes("pdf") || /\.pdf$/i.test(doc.filename)) return "pdf";
  if (type.startsWith("image/") || IMAGE_EXT.test(doc.filename)) return "image";
  return "other";
}
