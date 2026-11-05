import { useEffect, useState } from "react";
import { apiErrorDetail } from "@/lib/api/client";
import { courtOrdersApi } from "@/lib/api/court-orders";
import { documentsApi } from "@/lib/api/documents";
import { orderForDocument } from "@/lib/viewer-source";
import { resolveFileUrl } from "@/lib/utils";
import type { CourtOrder, Document } from "@/types";

export type DocumentFileState =
  | { status: "loading" }
  | { status: "ready"; blob: Blob; url: string }
  | { status: "error"; message: string };

/** The document's bytes.
 *
 * An eCourts order is streamed by the auth-checked orders endpoint with the
 * token header. Any other document only has the download endpoint, which
 * returns a storage URL (a short-lived presigned one in production): that
 * URL carries its own authorisation and is fetched here, without our token
 * (a second Authorization header would invalidate an S3 signature), and
 * handed to the viewer as a blob -- the storage URL itself is never put in
 * the page. */
async function fetchDocumentBlob(documentId: number, orderId: number | undefined): Promise<Blob> {
  if (orderId !== undefined) return courtOrdersApi.fetchFile(orderId);

  const { url } = await documentsApi.getDownloadUrl(documentId);
  const response = await fetch(resolveFileUrl(url), { credentials: "omit" });
  if (!response.ok) throw new Error(`The file could not be fetched (${response.status}).`);
  return response.blob();
}

/** Loads a document's file for the viewer and holds it as an object URL.
 *
 * The URL is revoked when the document changes or the viewer closes. */
export function useDocumentFile(
  doc: Document | undefined,
  orders: readonly CourtOrder[],
): DocumentFileState {
  const documentId = doc?.id;
  const orderId = doc ? orderForDocument(doc, orders)?.id : undefined;
  const [state, setState] = useState<DocumentFileState>({ status: "loading" });

  useEffect(() => {
    if (documentId === undefined) return;
    let cancelled = false;
    let objectUrl: string | null = null;
    setState({ status: "loading" });

    fetchDocumentBlob(documentId, orderId)
      .then((blob) => {
        if (cancelled) return;
        objectUrl = URL.createObjectURL(blob);
        setState({ status: "ready", blob, url: objectUrl });
      })
      .catch((error) => {
        if (cancelled) return;
        setState({
          status: "error",
          message:
            error instanceof Error && !("status" in error)
              ? error.message
              : apiErrorDetail(error, "This file could not be loaded."),
        });
      });

    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [documentId, orderId]);

  return state;
}
