/**
 * Flip to false to pull the guided tour without deleting anything: the
 * /walkthrough route renders a "not available" notice instead of the tour,
 * and the "Guided tour" entry in the Help menu hides itself.
 */
export const WALKTHROUGH_ENABLED = true;

/**
 * The advocate-wide Case Bot ("Ask about your practice") on the dashboard.
 * It does not exist yet, so this is off unless NEXT_PUBLIC_PORTFOLIO_BOT is
 * "true"; the dashboard looks complete without it and reserves the slot in
 * components/dashboard/portfolio-bot-slot.tsx.
 */
export const PORTFOLIO_BOT_ENABLED = process.env.NEXT_PUBLIC_PORTFOLIO_BOT === "true";

/**
 * Case drafting ("Draft with assistant" on the case page). Off unless
 * NEXT_PUBLIC_CASE_DRAFTING is "true". Saved case notes stay visible either way.
 */
export const CASE_DRAFTING_ENABLED = process.env.NEXT_PUBLIC_CASE_DRAFTING === "true";
