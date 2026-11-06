/** Where the advocate-wide Case Bot ("Ask about your practice") will go.
 *
 * It is the planned portfolio-level chat across every case and it does not
 * exist yet -- there is no endpoint, and nothing here pretends otherwise.
 * The briefing renders this only when NEXT_PUBLIC_PORTFOLIO_BOT is "true"
 * (see lib/feature-flags.ts); with the flag off, as it ships, the layout is
 * complete without it. When the feature is built, render it here. */
export function PortfolioBotSlot() {
  return null;
}
