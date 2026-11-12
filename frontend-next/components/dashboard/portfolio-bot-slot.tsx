import { PracticeContainer } from "@/components/dashboard/practice/practice-container";

/** The advocate-wide assistant and compact calendar on the dashboard.
 * The briefing and the phone dashboard render this only when
 * NEXT_PUBLIC_PORTFOLIO_BOT is "true" (see lib/feature-flags.ts); with the
 * flag off, as it ships, the layout is complete without it. The server has
 * its own switch: when that is off the container renders nothing. */
export function PortfolioBotSlot() {
  return <PracticeContainer />;
}
