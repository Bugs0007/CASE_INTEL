"use client";

import { PortfolioSummary, type PortfolioSummaryProps } from "./portfolio-summary";
import { PracticeAskBar } from "./practice-ask-bar";
import { PracticeWeekCalendar, type PracticeWeekCalendarProps } from "./practice-week-calendar";

export interface PracticeSectionProps {
  calendar: PracticeWeekCalendarProps;
  portfolio: PortfolioSummaryProps;
  /** A question typed in the ask bar; the Case Bot answers it. */
  onAsk: (question: string) => void;
}

/** The dashboard's practice block: an ask bar, then the week calendar and a
 * short cases summary in two equal columns (stacked on a phone). Each part
 * has its own loading and error state, so one failing never hides another.
 * The chatting itself happens in the Case Bot. */
export function PracticeSection({ calendar, portfolio, onAsk }: PracticeSectionProps) {
  return (
    <section aria-label="Your practice" className="min-w-0 space-y-3">
      <PracticeAskBar onAsk={onAsk} />
      <div className="grid min-w-0 grid-cols-1 items-stretch gap-4 lg:grid-cols-2">
        <div className="min-w-0">
          <PracticeWeekCalendar {...calendar} />
        </div>
        <div className="min-w-0">
          <PortfolioSummary {...portfolio} />
        </div>
      </div>
    </section>
  );
}
