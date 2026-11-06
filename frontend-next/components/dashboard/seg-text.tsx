import Link from "next/link";
import type { Seg } from "@/lib/dashboard/model";

/** Renders a sentence made of pieces (lib/dashboard/model.ts): the case
 * title as a link to the case, emphasis in italics, the amount owed in
 * bold, the rest plain. */
export function SegText({ segs }: { segs: readonly Seg[] }) {
  return (
    <>
      {segs.map((seg, i) => {
        switch (seg.kind) {
          case "case":
            return (
              <Link
                key={i}
                href={`/cases/${seg.caseId}`}
                className="font-bold text-gray-900 underline decoration-[#c9bd9c] decoration-1 underline-offset-[3px] hover:decoration-[var(--ci-ink)]"
              >
                {seg.text}
              </Link>
            );
          case "em":
            return (
              <em key={i} className="italic text-gray-700">
                {seg.text}
              </em>
            );
          case "strong":
            return (
              <strong key={i} className="font-bold">
                {seg.text}
              </strong>
            );
          default:
            return <span key={i}>{seg.text}</span>;
        }
      })}
    </>
  );
}

/** Small action buttons used inside the briefing. The first on a line is
 * dark; the rest are light. */
export const MINI_BUTTON =
  "inline-flex h-9 items-center justify-center rounded border px-2.5 text-xs font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-50 md:h-7";
export const MINI_BUTTON_DARK = `${MINI_BUTTON} border-[var(--ci-ink)] bg-[var(--ci-ink)] text-[color:var(--ci-paper)] hover:border-[var(--ci-seal)] hover:bg-[var(--ci-seal)]`;
export const MINI_BUTTON_LIGHT = `${MINI_BUTTON} border-[var(--ci-ink-14)] bg-surface text-gray-900 hover:border-[var(--ci-ink)]`;
