"use client";

import { useEffect, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { ClipboardCheck, Download, Loader2, RefreshCw, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { showToast } from "@/components/ui/toaster";
import {
  useDownloadDigestPdf,
  useHearingDigest,
  useRequestBriefing,
} from "@/hooks/use-hearing-digest";
import { formatHearingDate, formatRelativeTime } from "@/lib/utils";
import { daysUntilDate, dueChipVariant, dueLabel } from "@/lib/tasks";
import type { HearingDigest } from "@/types";

interface HearingDigestDialogProps {
  /** The hearing to prepare for; null keeps the dialog closed. */
  hearingId: number | null;
  onClose: () => void;
}

/** Everything needed for one hearing on one screen: cause-list position,
 * the last order and its directions, open tasks, documents on file, and a
 * short AI briefing on the state of the matter. Downloadable as a PDF. */
export function HearingDigestDialog({ hearingId, onClose }: HearingDigestDialogProps) {
  const { data: digest, isLoading, isError } = useHearingDigest(hearingId);
  const requestBriefing = useRequestBriefing();
  const downloadPdf = useDownloadDigestPdf();
  const requestedFor = useRef<number | null>(null);

  // Opening the sheet is the advocate preparing for this hearing, so a
  // missing or out-of-date briefing is requested once, automatically. A
  // failed one waits for "Try again" so a broken provider can't loop.
  const briefingStatus = digest?.briefing.status;
  useEffect(() => {
    if (hearingId === null || requestedFor.current === hearingId) return;
    if (briefingStatus === "missing" || briefingStatus === "stale") {
      requestedFor.current = hearingId;
      requestBriefing.mutate(hearingId);
    }
  }, [hearingId, briefingStatus, requestBriefing]);

  useEffect(() => {
    if (hearingId === null) {
      requestedFor.current = null;
      return;
    }
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handleEscape);
    return () => document.removeEventListener("keydown", handleEscape);
  }, [hearingId, onClose]);

  if (hearingId === null || typeof document === "undefined") return null;

  const handleDownload = () => {
    if (!digest) return;
    const caseRef = digest.case.case_number.replace(/[^A-Za-z0-9]+/g, "-");
    const day = digest.hearing.hearing_date.slice(0, 10);
    downloadPdf.mutate(
      { hearingId, filename: `prep-${caseRef}-${day}.pdf` },
      {
        onError: (error) => {
          console.error("Failed to download prep sheet:", error);
          showToast.error("Could not download the PDF", "Try again in a moment.");
        },
      },
    );
  };

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div
        className="absolute inset-0 bg-black/50 backdrop-blur-sm"
        onClick={onClose}
        aria-hidden="true"
      />
      <div
        className="relative bg-white rounded-xl shadow-xl w-full max-w-2xl mx-4 max-h-[90vh] flex flex-col"
        role="dialog"
        aria-modal="true"
        aria-labelledby="hearing-digest-title"
      >
        <div className="flex items-center justify-between gap-3 px-6 py-4 border-b border-gray-100">
          <div className="flex items-center gap-3 min-w-0">
            <div className="p-2 bg-gray-100 rounded-lg flex-shrink-0">
              <ClipboardCheck className="h-5 w-5 text-gray-700" />
            </div>
            <div className="min-w-0">
              <h2 id="hearing-digest-title" className="text-lg font-semibold text-gray-900">
                Hearing prep sheet
              </h2>
              {digest && (
                <p className="text-xs text-gray-500 truncate">
                  <span className="font-mono">{formatHearingDate(digest.hearing.hearing_date)}</span>
                  {" · "}
                  {digest.case.case_number}
                </p>
              )}
            </div>
          </div>
          <div className="flex items-center gap-1 flex-shrink-0">
            <Button
              variant="secondary"
              size="sm"
              onClick={handleDownload}
              disabled={!digest || downloadPdf.isPending}
            >
              {downloadPdf.isPending ? (
                <Loader2 className="h-4 w-4 mr-1 animate-spin" />
              ) : (
                <Download className="h-4 w-4 mr-1" />
              )}
              PDF
            </Button>
            <button
              onClick={onClose}
              className="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
              aria-label="Close prep sheet"
            >
              <X className="h-5 w-5" />
            </button>
          </div>
        </div>

        <div className="overflow-y-auto px-6 py-5 space-y-6">
          {isLoading && <p className="text-sm text-gray-500">Preparing…</p>}
          {isError && (
            <p className="text-sm text-status-alert">Could not load the prep sheet.</p>
          )}
          {digest && (
            <DigestBody
              digest={digest}
              onRequestBriefing={() => requestBriefing.mutate(hearingId)}
              isRequesting={requestBriefing.isPending}
            />
          )}
        </div>
      </div>
    </div>,
    document.body,
  );
}

function DigestBody({
  digest,
  onRequestBriefing,
  isRequesting,
}: {
  digest: HearingDigest;
  onRequestBriefing: () => void;
  isRequesting: boolean;
}) {
  const { hearing, case: caseInfo, last_order: lastOrder } = digest;
  const cause = hearing.cause_list;
  const causeListText =
    cause.status === "listed"
      ? [
          cause.item_number && `Item ${cause.item_number}`,
          cause.court_hall && `Court hall ${cause.court_hall}`,
          cause.stage,
        ]
          .filter(Boolean)
          .join(" · ") || "Listed"
      : cause.status === "not_checked"
        ? ""
        : cause.status_display;

  const facts: [string, string][] = [
    ["For", digest.purposes.join("; ")],
    ["Court", caseInfo.court_and_judge || hearing.location],
    ["Cause list", causeListText],
    ["Case status", [caseInfo.case_status, caseInfo.case_stage].filter(Boolean).join(" / ")],
  ];

  return (
    <>
      <dl className="grid grid-cols-[7rem_1fr] gap-x-4 gap-y-1.5 text-sm">
        {facts
          .filter(([, value]) => value)
          .map(([label, value]) => (
            <div key={label} className="contents">
              <dt className="text-gray-500">{label}</dt>
              <dd className="text-gray-900">{value}</dd>
            </div>
          ))}
      </dl>

      <Section title="State of the matter">
        <Briefing digest={digest} onRequest={onRequestBriefing} isRequesting={isRequesting} />
      </Section>

      {lastOrder && (
        <Section
          title={`Last order${lastOrder.order_date ? ` · ${formatHearingDate(lastOrder.order_date)}` : ""}`}
        >
          {lastOrder.summary.what_happened && (
            <p className="text-sm text-gray-700">{lastOrder.summary.what_happened}</p>
          )}
          <Directions summary={lastOrder.summary} />
        </Section>
      )}

      <Section title="Open tasks & deadlines">
        {digest.open_tasks.length === 0 ? (
          <p className="text-sm text-gray-500">None open.</p>
        ) : (
          <ul className="space-y-2">
            {digest.open_tasks.map((task) => {
              const days = task.due_date ? daysUntilDate(task.due_date) : null;
              return (
                <li key={task.id} className="flex items-start gap-2 text-sm">
                  {days !== null ? (
                    <span className={`ci-chip ci-chip--${dueChipVariant(days)} flex-shrink-0`}>
                      {dueLabel(days)}
                    </span>
                  ) : (
                    <span className="ci-chip ci-chip--none flex-shrink-0">No date</span>
                  )}
                  <span className="text-gray-900">{task.title}</span>
                </li>
              );
            })}
          </ul>
        )}
      </Section>

      <Section title="Documents on file">
        {digest.documents.length === 0 ? (
          <p className="text-sm text-gray-500">None uploaded.</p>
        ) : (
          <ul className="space-y-1 text-sm text-gray-900">
            {digest.documents.map((document) => (
              <li key={document.id}>
                {document.filename}
                {document.document_type_display && (
                  <span className="text-gray-500"> · {document.document_type_display}</span>
                )}
              </li>
            ))}
          </ul>
        )}
      </Section>

      <p className="text-xs text-gray-400">
        Court tracking data{" "}
        {caseInfo.last_fetched_at
          ? `refreshed ${formatRelativeTime(caseInfo.last_fetched_at)}`
          : "never refreshed"}
        . Check the court record before relying on this sheet.
      </p>
    </>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="space-y-2">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-gray-500">{title}</h3>
      {children}
    </section>
  );
}

function Briefing({
  digest,
  onRequest,
  isRequesting,
}: {
  digest: HearingDigest;
  onRequest: () => void;
  isRequesting: boolean;
}) {
  const { status, text, generated_at: generatedAt, error } = digest.briefing;

  if (status === "unavailable") {
    return <p className="text-sm text-gray-500">Nothing on record yet to summarise.</p>;
  }

  const outOfDate = status !== "ready" && Boolean(text);

  return (
    <div className="space-y-2">
      {text && (
        <p className={`text-sm ${outOfDate ? "text-gray-500" : "text-gray-800"}`}>{text}</p>
      )}

      <div className="flex items-center gap-2 flex-wrap text-xs text-gray-500">
        {status === "ready" && generatedAt && <span>AI briefing · {formatRelativeTime(generatedAt)}</span>}
        {(status === "generating" || isRequesting) && (
          <span className="flex items-center gap-1">
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
            {text ? "Updating with the latest changes…" : "Writing the briefing…"}
          </span>
        )}
        {status === "stale" && !isRequesting && (
          <span className="ci-chip ci-chip--pending">Out of date</span>
        )}
        {status === "failed" && (
          <span className="text-status-alert" title={error}>
            The briefing could not be generated.
          </span>
        )}
        {(status === "failed" || status === "stale" || status === "missing") && !isRequesting && (
          <Button variant="ghost" size="sm" onClick={onRequest}>
            <RefreshCw className="h-3.5 w-3.5 mr-1" />
            {status === "failed" ? "Try again" : "Generate"}
          </Button>
        )}
      </div>
    </div>
  );
}

function Directions({ summary }: { summary: NonNullable<HearingDigest["last_order"]>["summary"] }) {
  const sides: [string, string[]][] =
    summary.your_side_directions !== null
      ? [
          [summary.your_side_label ?? "Your side", summary.your_side_directions],
          [summary.other_side_label ?? "Other side", summary.other_side_directions ?? []],
        ]
      : [
          ["Petitioner", summary.petitioner_directions],
          ["Respondent", summary.respondent_directions],
        ];

  const withDirections = sides.filter(([, directions]) => directions.length > 0);
  if (withDirections.length === 0) return null;

  return (
    <div className="space-y-2">
      {withDirections.map(([label, directions]) => (
        <div key={label}>
          <div className="text-xs font-medium text-gray-500">{label}</div>
          <ul className="list-disc pl-5 text-sm text-gray-800 space-y-0.5">
            {directions.map((direction) => (
              <li key={direction}>{direction}</li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}
