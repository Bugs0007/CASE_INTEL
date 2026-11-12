"use client";

import { useState } from "react";
import { BottomSheet } from "@/components/ui/bottom-sheet";
import { Button } from "@/components/ui/button";
import { useIsMobile } from "@/hooks/use-is-mobile";
import { PortfolioSummary, type PortfolioSummaryProps } from "./portfolio-summary";
import {
  PracticeAssistantPanel,
  PracticeMessageList,
  type PracticeAssistantPanelProps,
} from "./practice-assistant-panel";
import { PracticeWeekCalendar, type PracticeWeekCalendarProps } from "./practice-week-calendar";

/** On a phone the thread shows its latest exchange inline; the rest opens in a sheet. */
const INLINE_MESSAGES_ON_PHONE = 2;

export interface PracticeSectionProps {
  calendar: PracticeWeekCalendarProps;
  portfolio: PortfolioSummaryProps;
  assistant: PracticeAssistantPanelProps;
}

/** The dashboard's practice block. Each part has its own loading and error
 * state, so one failing never hides another. Desktop puts the calendar and
 * summary beside the assistant; a phone stacks them. */
export function PracticeSection({ calendar, portfolio, assistant }: PracticeSectionProps) {
  const isMobile = useIsMobile();
  const [historyOpen, setHistoryOpen] = useState(false);

  const earlier = isMobile ? assistant.messages.slice(0, -INLINE_MESSAGES_ON_PHONE) : [];
  const inline = isMobile ? assistant.messages.slice(-INLINE_MESSAGES_ON_PHONE) : assistant.messages;

  return (
    <section aria-label="Your practice" className="grid min-w-0 grid-cols-1 gap-4 lg:grid-cols-2">
      <div className="min-w-0 space-y-4">
        <PracticeWeekCalendar {...calendar} />
        <PortfolioSummary {...portfolio} />
      </div>
      <div className="min-w-0 space-y-2">
        {earlier.length > 0 && (
          <Button type="button" variant="secondary" size="sm" className="w-full" onClick={() => setHistoryOpen(true)}>
            Earlier messages ({earlier.length})
          </Button>
        )}
        <PracticeAssistantPanel {...assistant} messages={inline} />
      </div>
      <BottomSheet open={historyOpen && earlier.length > 0} onClose={() => setHistoryOpen(false)} label="Earlier messages">
        <div className="p-4">
          <PracticeMessageList
            messages={earlier}
            onChooseCase={assistant.onChooseCase}
            onConfirmInvoice={assistant.onConfirmInvoice}
            onDismissAction={assistant.onDismissAction}
            confirmingFeeId={assistant.confirmingFeeId}
          />
        </div>
      </BottomSheet>
    </section>
  );
}
