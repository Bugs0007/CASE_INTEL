"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { apiErrorDetail } from "@/lib/api/client";
import { practiceApi } from "@/lib/api/practice";
import type { PracticeReportCard as ReportCard, PracticeReportFormat } from "@/types/practice";

const BLOB_REVOKE_DELAY_MS = 10_000;
const FORMAT_LABEL: Record<PracticeReportFormat, string> = { pdf: "Download PDF", docx: "Download DOCX" };

function formatDay(day: string): string {
  const [y, m, d] = day.split("-").map(Number);
  if (!y || !m || !d) return day;
  return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString("en-IN", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  });
}

function periodText(card: ReportCard): string {
  if (card.date_from && card.date_to) return `${formatDay(card.date_from)} to ${formatDay(card.date_to)}`;
  if (card.date_from) return `From ${formatDay(card.date_from)}`;
  if (card.date_to) return `Up to ${formatDay(card.date_to)}`;
  return "All dates";
}

/** A finished report. Reading it changes nothing; each button fetches the
 * file for the card's own kind and dates with the auth header and saves it. */
export function PracticeReportCard({ card }: { card: ReportCard }) {
  const [busy, setBusy] = useState<PracticeReportFormat | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function download(format: PracticeReportFormat) {
    if (busy) return;
    setBusy(format);
    setError(null);
    try {
      const blob = await practiceApi.report(card, format);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${card.kind}-report.${format}`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(url), BLOB_REVOKE_DELAY_MS);
    } catch (caught) {
      setError(apiErrorDetail(caught, "The report could not be downloaded. Try again."));
    } finally {
      setBusy(null);
    }
  }

  return (
    <section aria-label="Report" className="space-y-2 rounded-lg border border-gray-200 bg-surface p-3">
      <h4 className="break-words text-sm font-semibold text-gray-900">{card.title}</h4>
      <p className="text-sm text-gray-600">
        {periodText(card)}. {card.row_count === 1 ? "1 row" : `${card.row_count} rows`}.
      </p>
      {error && (
        <p role="alert" className="rounded-lg bg-red-50 p-2 text-sm text-red-800">
          {error}
        </p>
      )}
      <div className="flex flex-wrap gap-2">
        {card.formats.map((format) => (
          <Button
            key={format}
            type="button"
            size="sm"
            variant="secondary"
            disabled={busy !== null}
            onClick={() => download(format)}
          >
            {FORMAT_LABEL[format]}
          </Button>
        ))}
      </div>
    </section>
  );
}
