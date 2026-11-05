/** pdf.js, loaded on first use.
 *
 * Dynamic import, so none of it is in the case page's bundle: it is fetched
 * when a PDF is first opened in the viewer. The worker is a separate file
 * the bundler emits next to it. */
let loading: Promise<typeof import("pdfjs-dist")> | null = null;

export function loadPdfjs(): Promise<typeof import("pdfjs-dist")> {
  if (!loading) {
    loading = import("pdfjs-dist")
      .then((pdfjs) => {
        pdfjs.GlobalWorkerOptions.workerSrc = new URL(
          "pdfjs-dist/build/pdf.worker.min.mjs",
          import.meta.url,
        ).toString();
        return pdfjs;
      })
      .catch((error) => {
        loading = null; // let the next open try again
        throw error;
      });
  }
  return loading;
}
