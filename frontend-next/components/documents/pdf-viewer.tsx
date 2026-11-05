"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ChevronDown,
  ChevronUp,
  Loader2,
  MoveHorizontal,
  Search,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import type { PDFDocumentProxy } from "pdfjs-dist";
import { Button } from "@/components/ui/button";
import { loadPdfjs } from "@/lib/pdfjs";
import {
  findPageMatches,
  matchRect,
  type HighlightRect,
  type TextItemLite,
} from "@/lib/pdf-text";

const MIN_ZOOM = 0.5;
const MAX_ZOOM = 3;
const ZOOM_STEP = 0.25;
const PAGE_GAP = 12;
const SIDE_PADDING = 32;
/** Pages this far (px) above or below the viewport are drawn; the rest are
 * blank placeholders, so a 200-page order never holds 200 canvases. */
const RENDER_MARGIN = 1200;
const MAX_PIXEL_RATIO = 2;

interface Size {
  width: number;
  height: number;
}

interface Occurrence {
  page: number;
  rects: HighlightRect[];
}

interface PdfViewerProps {
  blob: Blob;
}

/** A PDF, drawn by pdf.js: page navigation, zoom and fit-width, and a text
 * search that highlights where it matches. Only the pages near the viewport
 * are rendered. */
export default function PdfViewer({ blob }: PdfViewerProps) {
  const [pdf, setPdf] = useState<PDFDocumentProxy | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [pageSizes, setPageSizes] = useState<Record<number, Size>>({});
  const [zoom, setZoom] = useState<number | "fit">("fit");
  const [containerWidth, setContainerWidth] = useState(0);
  const [currentPage, setCurrentPage] = useState(1);
  const [pageInput, setPageInput] = useState("1");

  const [query, setQuery] = useState("");
  const [occurrences, setOccurrences] = useState<Occurrence[]>([]);
  const [searching, setSearching] = useState(false);
  const [activeHit, setActiveHit] = useState(0);

  const scrollRef = useRef<HTMLDivElement>(null);
  const pageRefs = useRef<Record<number, HTMLDivElement | null>>({});
  const textCache = useRef<Map<number, { items: TextItemLite[]; transform: number[] }>>(new Map());

  // Load the document.
  useEffect(() => {
    let cancelled = false;
    // Destroying the loading task also releases the document it produced.
    let task: { destroy: () => Promise<void> | void } | null = null;
    setPdf(null);
    setLoadError(null);
    setPageSizes({});
    setCurrentPage(1);
    setPageInput("1");
    setQuery("");
    setOccurrences([]);
    textCache.current = new Map();

    (async () => {
      try {
        const pdfjs = await loadPdfjs();
        const data = await blob.arrayBuffer();
        if (cancelled) return;
        const loadingTask = pdfjs.getDocument({ data });
        task = loadingTask;
        const doc = await loadingTask.promise;
        if (cancelled) return;
        const first = await doc.getPage(1);
        const viewport = first.getViewport({ scale: 1 });
        if (cancelled) return;
        setPageSizes({ 1: { width: viewport.width, height: viewport.height } });
        setPdf(doc);
      } catch (error) {
        if (!cancelled) {
          console.error("Failed to open PDF:", error);
          setLoadError("This PDF could not be displayed. You can still download it.");
        }
      }
    })();

    return () => {
      cancelled = true;
      void task?.destroy();
    };
  }, [blob]);

  // Track the scroll area's width for fit-width.
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    setContainerWidth(el.clientWidth);
    const observer = new ResizeObserver(() => setContainerWidth(el.clientWidth));
    observer.observe(el);
    return () => observer.disconnect();
  }, [pdf]);

  const firstSize = pageSizes[1];
  const scale = useMemo(() => {
    if (zoom !== "fit") return zoom;
    if (!firstSize || containerWidth <= 0) return 1;
    return Math.min(Math.max((containerWidth - SIDE_PADDING) / firstSize.width, 0.3), 4);
  }, [zoom, firstSize, containerWidth]);

  const numPages = pdf?.numPages ?? 0;

  const goToPage = useCallback(
    (page: number) => {
      const clamped = Math.min(Math.max(page, 1), Math.max(numPages, 1));
      pageRefs.current[clamped]?.scrollIntoView({ block: "start" });
      setCurrentPage(clamped);
      setPageInput(String(clamped));
    },
    [numPages],
  );

  // Which page is at the top of the viewport.
  const onScroll = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    const threshold = el.getBoundingClientRect().top + el.clientHeight * 0.3;
    let found = 1;
    for (let n = 1; n <= numPages; n++) {
      const page = pageRefs.current[n];
      if (!page) continue;
      if (page.getBoundingClientRect().top <= threshold) found = n;
      else break;
    }
    setCurrentPage(found);
    setPageInput(String(found));
  }, [numPages]);

  // Search every page's text (cached), after a short pause in typing.
  useEffect(() => {
    if (!pdf) return;
    const needle = query.trim();
    if (!needle) {
      setOccurrences([]);
      setSearching(false);
      return;
    }
    let cancelled = false;
    setSearching(true);
    const timer = window.setTimeout(async () => {
      const found: Occurrence[] = [];
      try {
        for (let n = 1; n <= pdf.numPages && !cancelled; n++) {
          let text = textCache.current.get(n);
          if (!text) {
            const page = await pdf.getPage(n);
            const content = await page.getTextContent();
            text = {
              items: content.items.filter((item) => "str" in item) as unknown as TextItemLite[],
              transform: page.getViewport({ scale: 1 }).transform,
            };
            textCache.current.set(n, text);
          }
          const pieces = findPageMatches(text.items, needle);
          const byOccurrence = new Map<number, HighlightRect[]>();
          for (const piece of pieces) {
            const rects = byOccurrence.get(piece.occurrence) ?? [];
            rects.push(matchRect(text.items[piece.item], piece, text.transform));
            byOccurrence.set(piece.occurrence, rects);
          }
          for (const rects of byOccurrence.values()) found.push({ page: n, rects });
        }
      } catch (error) {
        console.error("PDF search failed:", error);
      }
      if (cancelled) return;
      setOccurrences(found);
      setActiveHit(0);
      setSearching(false);
      if (found.length > 0) goToPage(found[0].page);
    }, 300);

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
    // goToPage changes only with the page count, which is fixed per document.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query, pdf]);

  const stepHit = (delta: number) => {
    if (occurrences.length === 0) return;
    const next = (activeHit + delta + occurrences.length) % occurrences.length;
    setActiveHit(next);
    goToPage(occurrences[next].page);
  };

  const zoomBy = (delta: number) => {
    const base = zoom === "fit" ? scale : zoom;
    setZoom(Math.min(Math.max(Math.round((base + delta) * 100) / 100, MIN_ZOOM), MAX_ZOOM));
  };

  if (loadError) {
    return (
      <div className="flex flex-1 items-center justify-center p-6 text-center text-sm text-gray-600">
        {loadError}
      </div>
    );
  }
  if (!pdf || !firstSize) {
    return (
      <div className="flex flex-1 items-center justify-center gap-2 text-sm text-gray-500">
        <Loader2 className="h-4 w-4 animate-spin" />
        Opening PDF…
      </div>
    );
  }

  const highlightsByPage = new Map<number, { rects: HighlightRect[]; active: boolean }[]>();
  occurrences.forEach((occurrence, index) => {
    const list = highlightsByPage.get(occurrence.page) ?? [];
    list.push({ rects: occurrence.rects, active: index === activeHit });
    highlightsByPage.set(occurrence.page, list);
  });

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div
        role="toolbar"
        aria-label="PDF controls"
        className="flex flex-shrink-0 flex-wrap items-center gap-x-4 gap-y-2 border-b border-gray-100 bg-surface px-3 py-2"
      >
        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="sm"
            className="px-2"
            onClick={() => goToPage(currentPage - 1)}
            disabled={currentPage <= 1}
            aria-label="Previous page"
          >
            <ChevronUp className="h-4 w-4" />
          </Button>
          <label className="flex items-center gap-1 text-sm text-gray-600">
            <span className="sr-only">Page</span>
            <input
              value={pageInput}
              inputMode="numeric"
              aria-label="Page number"
              onChange={(e) => setPageInput(e.target.value.replace(/\D/g, ""))}
              onKeyDown={(e) => {
                if (e.key === "Enter" && pageInput) goToPage(Number(pageInput));
              }}
              onBlur={() => setPageInput(String(currentPage))}
              className="h-8 w-12 rounded-lg border border-gray-200 bg-surface text-center text-sm"
            />
            <span>/ {numPages}</span>
          </label>
          <Button
            variant="ghost"
            size="sm"
            className="px-2"
            onClick={() => goToPage(currentPage + 1)}
            disabled={currentPage >= numPages}
            aria-label="Next page"
          >
            <ChevronDown className="h-4 w-4" />
          </Button>
        </div>

        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="sm"
            className="px-2"
            onClick={() => zoomBy(-ZOOM_STEP)}
            disabled={scale <= MIN_ZOOM}
            aria-label="Zoom out"
          >
            <ZoomOut className="h-4 w-4" />
          </Button>
          <span className="w-12 text-center text-sm text-gray-600" aria-live="polite">
            {Math.round(scale * 100)}%
          </span>
          <Button
            variant="ghost"
            size="sm"
            className="px-2"
            onClick={() => zoomBy(ZOOM_STEP)}
            disabled={scale >= MAX_ZOOM}
            aria-label="Zoom in"
          >
            <ZoomIn className="h-4 w-4" />
          </Button>
          <Button
            variant={zoom === "fit" ? "secondary" : "ghost"}
            size="sm"
            onClick={() => setZoom("fit")}
            aria-pressed={zoom === "fit"}
          >
            <MoveHorizontal className="h-4 w-4" />
            Fit width
          </Button>
        </div>

        <div className="flex items-center gap-1">
          <div className="relative">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
            <input
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") stepHit(e.shiftKey ? -1 : 1);
                if (e.key === "Escape" && query) {
                  e.stopPropagation();
                  setQuery("");
                }
              }}
              placeholder="Find in document"
              aria-label="Find in document"
              className="h-8 w-44 rounded-lg border border-gray-200 bg-surface pl-8 pr-2 text-sm"
            />
          </div>
          <span className="min-w-[4.5rem] text-xs text-gray-500" aria-live="polite">
            {searching
              ? "Searching…"
              : query.trim()
                ? occurrences.length === 0
                  ? "No matches"
                  : `${activeHit + 1} of ${occurrences.length}`
                : ""}
          </span>
          <Button
            variant="ghost"
            size="sm"
            className="px-2"
            onClick={() => stepHit(-1)}
            disabled={occurrences.length === 0}
            aria-label="Previous match"
          >
            <ChevronUp className="h-4 w-4" />
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="px-2"
            onClick={() => stepHit(1)}
            disabled={occurrences.length === 0}
            aria-label="Next match"
          >
            <ChevronDown className="h-4 w-4" />
          </Button>
        </div>
      </div>

      <div
        ref={scrollRef}
        onScroll={onScroll}
        className="min-h-0 flex-1 overflow-auto bg-gray-100"
        data-testid="pdf-scroll"
      >
        <div
          className="mx-auto flex w-max min-w-full flex-col items-center py-3"
          style={{ gap: PAGE_GAP }}
        >
          {Array.from({ length: numPages }, (_, i) => i + 1).map((pageNumber) => (
            <PdfPage
              key={pageNumber}
              pdf={pdf}
              pageNumber={pageNumber}
              scale={scale}
              size={pageSizes[pageNumber] ?? firstSize}
              scrollRoot={scrollRef}
              highlights={highlightsByPage.get(pageNumber)}
              registerRef={(el) => {
                pageRefs.current[pageNumber] = el;
              }}
              onSize={(size) =>
                setPageSizes((prev) =>
                  prev[pageNumber]?.width === size.width && prev[pageNumber]?.height === size.height
                    ? prev
                    : { ...prev, [pageNumber]: size },
                )
              }
            />
          ))}
        </div>
      </div>
    </div>
  );
}

interface PdfPageProps {
  pdf: PDFDocumentProxy;
  pageNumber: number;
  scale: number;
  size: Size;
  scrollRoot: React.RefObject<HTMLDivElement | null>;
  highlights?: { rects: HighlightRect[]; active: boolean }[];
  registerRef: (el: HTMLDivElement | null) => void;
  onSize: (size: Size) => void;
}

function PdfPage({
  pdf,
  pageNumber,
  scale,
  size,
  scrollRoot,
  highlights,
  registerRef,
  onSize,
}: PdfPageProps) {
  const wrapperRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [near, setNear] = useState(pageNumber <= 2);

  // Draw only while within RENDER_MARGIN of the viewport.
  useEffect(() => {
    const el = wrapperRef.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      ([entry]) => setNear(entry.isIntersecting),
      { root: scrollRoot.current, rootMargin: `${RENDER_MARGIN}px 0px` },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [scrollRoot]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    if (!near) {
      canvas.width = 0;
      canvas.height = 0;
      return;
    }

    let cancelled = false;
    let renderTask: { cancel: () => void; promise: Promise<unknown> } | null = null;

    (async () => {
      try {
        const page = await pdf.getPage(pageNumber);
        if (cancelled) return;
        const base = page.getViewport({ scale: 1 });
        onSize({ width: base.width, height: base.height });

        const ratio = Math.min(window.devicePixelRatio || 1, MAX_PIXEL_RATIO);
        const viewport = page.getViewport({ scale: scale * ratio });
        const context = canvas.getContext("2d");
        if (!context) return;
        canvas.width = Math.floor(viewport.width);
        canvas.height = Math.floor(viewport.height);
        canvas.style.width = `${viewport.width / ratio}px`;
        canvas.style.height = `${viewport.height / ratio}px`;

        renderTask = page.render({ canvasContext: context, viewport, canvas });
        await renderTask.promise;
      } catch (error) {
        // A superseded render is cancelled on purpose.
        if ((error as { name?: string })?.name !== "RenderingCancelledException" && !cancelled) {
          console.error(`Failed to render page ${pageNumber}:`, error);
        }
      }
    })();

    return () => {
      cancelled = true;
      renderTask?.cancel();
    };
    // onSize is a fresh closure each render; the page only needs redrawing
    // when the document, the page or the scale changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pdf, pageNumber, scale, near]);

  return (
    <div
      ref={(el) => {
        wrapperRef.current = el;
        registerRef(el);
      }}
      role="group"
      aria-label={`Page ${pageNumber}`}
      className="relative flex-shrink-0 bg-white shadow-card"
      style={{ width: size.width * scale, height: size.height * scale }}
    >
      <canvas ref={canvasRef} className="block" />
      {highlights?.map((hit, hitIndex) =>
        hit.rects.map((rect, rectIndex) => (
          <div
            key={`${hitIndex}-${rectIndex}`}
            aria-hidden="true"
            className="pointer-events-none absolute rounded-sm"
            style={{
              left: rect.x * scale,
              top: rect.y * scale,
              width: rect.width * scale,
              height: rect.height * scale,
              background: hit.active
                ? "color-mix(in srgb, var(--ci-warn) 55%, transparent)"
                : "color-mix(in srgb, var(--ci-warn) 28%, transparent)",
              outline: hit.active ? "1px solid var(--ci-warn)" : undefined,
            }}
          />
        )),
      )}
    </div>
  );
}
